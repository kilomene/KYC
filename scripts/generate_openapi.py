#!/usr/bin/env python3
"""Generate the Nova KYC OpenAPI documents.

The operation inventory in this file is the contract's source of
truth for documentation generation. It mirrors the routes actually
implemented by ``server/app.py``; ``tests/test_openapi_docs.py``
compares the generated specification against a pinned inventory so
an endpoint cannot silently disappear from the developer docs.

Outputs (all generated; do not hand-edit):
  docs/openapi.json
  docs/openapi.yaml
  public/openapi.json
  public/openapi.yaml
"""
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def ref(name):
    return {"$ref": f"#/components/schemas/{name}"}


def array_of(name):
    return {"type": "array", "items": ref(name)}


def body(schema, required=True, examples=None):
    out = {
        "required": required,
        "content": {"application/json": {"schema": schema}},
    }
    if examples:
        out["content"]["application/json"]["examples"] = examples
    return out


def form_body(schema, required=True):
    return {
        "required": required,
        "content": {"multipart/form-data": {"schema": schema}},
    }


def path_param(name, description):
    return {
        "name": name,
        "in": "path",
        "required": True,
        "description": description,
        "schema": {"type": "string"},
    }


def query_param(name, description, schema=None, required=False):
    return {
        "name": name,
        "in": "query",
        "required": required,
        "description": description,
        "schema": schema or {"type": "string"},
    }


PARAMS = {
    "applicantId": path_param("applicantId", "Applicant UUID owned by the authenticated tenant and environment."),
    "sessionId": path_param("sessionId", "Verification session UUID owned by the authenticated tenant and environment."),
    "businessId": path_param("businessId", "Business UUID owned by the authenticated tenant and environment."),
    "caseId": path_param("caseId", "Review case UUID owned by the authenticated tenant and environment."),
    "hitId": path_param("hitId", "Screening-hit UUID belonging to the case."),
    "userId": path_param("userId", "Tenant user UUID."),
    "keyId": path_param("keyId", "API-key UUID belonging to the authenticated tenant."),
    "webhookId": path_param("webhookId", "Webhook endpoint UUID owned by the authenticated tenant and environment."),
    "deliveryId": path_param("deliveryId", "Webhook delivery UUID belonging to the authenticated tenant."),
    "documentId": path_param("documentId", "Stored document UUID owned by the authenticated tenant and environment."),
    "biometricId": path_param("biometricId", "Stored biometric capture UUID owned by the authenticated tenant and environment."),
    "tenantId": path_param("tenantId", "Tenant UUID. Platform-operator operations only."),
}

ERROR_DESCRIPTIONS = {
    400: "The request could not be parsed or is malformed.",
    401: "Authentication is missing, invalid, revoked, or not valid for this resource.",
    403: "The caller is authenticated but is not allowed to perform this operation.",
    404: "The resource does not exist, or it belongs to another tenant or environment.",
    409: "The current resource state conflicts with the requested operation.",
    413: "The request body exceeds the configured size limit.",
    416: "The requested media range is not satisfiable.",
    422: "Validation failed. Correct the named field or state and retry.",
    429: "A rate limit or monthly live-verification quota was reached.",
    500: "An internal error occurred. Retry with backoff and contact the operator if it persists.",
    503: "A required local capability or stored-data key is unavailable.",
}


def responses(success_status, success_schema=None, success_description="Success",
              errors=(401, 404, 422, 429), content_type="application/json",
              extra=None):
    if success_schema is None:
        content = {}
    elif isinstance(success_schema, dict) and success_schema.get("type") == "string":
        content = {content_type: {"schema": success_schema}}
    else:
        content = {content_type: {"schema": success_schema}}
    out = {
        str(success_status): {
            "description": success_description,
            "content": content,
        }
    }
    for status in errors:
        out[str(status)] = {
            "description": ERROR_DESCRIPTIONS[status],
            "content": {"application/json": {"schema": ref("Error")}},
            "headers": ({"Retry-After": {"$ref": "#/components/headers/RetryAfter"}}
                        if status == 429 else {}),
        }
    if 429 in errors:
        out["429"]["headers"] = {"Retry-After": {"$ref": "#/components/headers/RetryAfter"}}
    if extra:
        for status, response in extra.items():
            out[str(status)] = response
    return out


def operation(operation_id, tag, summary, security, success_status,
              success_schema=None, success_description="Success", parameters=None,
              request_body=None, errors=(401, 404, 422, 429), extra_responses=None,
              content_type="application/json"):
    # The operation inventory uses one carefully written text as both
    # the short summary and the fuller description. Keeping them the
    # same avoids a second, drifting paraphrase of the same contract.
    out = {
        "tags": [tag],
        "summary": summary,
        "description": summary,
        "operationId": operation_id,
        "security": security,
        "responses": responses(success_status, success_schema, success_description,
                               errors=errors, extra=extra_responses,
                               content_type=content_type),
    }
    if parameters:
        out["parameters"] = parameters
    if request_body:
        out["requestBody"] = request_body
    return out


TENANT = [{"tenantApiKey": []}]
PLATFORM = [{"platformAdmin": []}]
FLOW = [{"flowTokenBearer": []}, {"flowTokenHeader": []}]
NONE = []
REVIEWER_PARAMS = [
    {
        "name": "X-Reviewer-Key",
        "in": "header",
        "required": False,
        "description": "Optional named reviewer token issued by POST /v1/users. If present it must be valid; "
                       "without it, the tenant API-key identity is recorded as an admin reviewer.",
        "schema": {"type": "string"},
    },
    {
        "name": "X-Reviewer-TOTP",
        "in": "header",
        "required": False,
        "description": "Required conditionally when the named reviewer has MFA enabled, or when the deployment "
                       "requires MFA enrolment for privileged actions.",
        "schema": {"type": "string", "pattern": "^[0-9]{6}$"},
    },
]

COMPONENTS = {
    "securitySchemes": {
        "tenantApiKey": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "Nova KYC API key",
            "description": "Tenant API key. Test keys use the kyc_test_ prefix and live keys use kyc_live_; "
                           "the key selects the environment. Keep keys on a server only.",
        },
        "platformAdmin": {
            "type": "apiKey",
            "in": "header",
            "name": "X-Platform-Admin",
            "description": "Platform-operator token. Tenant creation and operator administration fail closed "
                           "when the server has no platform token configured.",
        },
        "flowTokenBearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "Hosted-flow token",
            "description": "Short-lived token returned when a session is created. It identifies one applicant "
                           "session only and is used by the hosted flow, not as a tenant credential.",
        },
        "flowTokenHeader": {
            "type": "apiKey",
            "in": "header",
            "name": "X-Flow-Token",
            "description": "Alternative presentation of the hosted-flow token.",
        },
    },
    "headers": {
        "RetryAfter": {
            "description": "Seconds until the rate-limit window frees a slot.",
            "schema": {"type": "integer", "minimum": 0},
        }
    },
    "schemas": {
        "Error": {
            "type": "object",
            "required": ["error"],
            "properties": {
                "error": {
                    "type": "object",
                    "required": ["code", "message"],
                    "properties": {
                        "code": {"type": "string", "example": "validation_error"},
                        "message": {"type": "string", "example": "country required"},
                    },
                    "additionalProperties": False,
                }
            },
            "additionalProperties": False,
        },
        "Environment": {"type": "string", "enum": ["test", "live"]},
        "IdentitySource": {"type": "string", "enum": ["declared", "document"]},
        "SessionStatus": {
            "type": "string",
            "enum": ["created", "in_progress", "processing", "approved", "rejected",
                     "needs_review", "needs_more_information", "expired", "cancelled"],
        },
        "CheckStatus": {
            "type": "string",
            "enum": ["pass", "fail", "unclear", "error", "not_run"],
        },
        "Applicant": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "tenant_id": {"type": "string", "format": "uuid"},
                "env": ref("Environment"),
                "external_ref": {"type": ["string", "null"], "description": "The integrating product's own user reference."},
                "first_name": {"type": ["string", "null"]},
                "last_name": {"type": ["string", "null"]},
                "dob": {"type": ["string", "null"], "format": "date"},
                "country": {"type": "string", "description": "ISO 3166-1 alpha-2 country code."},
                "email": {"type": ["string", "null"], "format": "email"},
                "phone": {"type": ["string", "null"]},
                "address_line": {"type": ["string", "null"]},
                "city": {"type": ["string", "null"]},
                "identity_source": ref("IdentitySource"),
                "identity_document_id": {"type": ["string", "null"], "format": "uuid"},
                "data_deleted_at": {"type": ["string", "null"], "format": "date-time"},
                "created_at": {"type": "string", "format": "date-time"},
                "updated_at": {"type": "string", "format": "date-time"},
            },
            "additionalProperties": True,
        },
        "ApplicantCreate": {
            "oneOf": [ref("ApplicantCreateDeclared"), ref("ApplicantCreateDocument")],
            "description": "Use the declared form only when the integrating product already has a lawful, reliable "
                           "name and date of birth to cross-check. The document form is the recommended default "
                           "because the platform reads identity from the presented document.",
        },
        "ApplicantCreateDeclared": {
            "type": "object",
            "required": ["first_name", "last_name", "dob", "country"],
            "properties": {
                "identity_source": {"type": "string", "enum": ["declared"], "default": "declared"},
                "first_name": {"type": "string", "example": "Adaeze"},
                "last_name": {"type": "string", "example": "Example"},
                "dob": {"type": "string", "format": "date", "example": "1992-04-17"},
                "country": {"type": "string", "example": "NG"},
                "external_ref": {"type": "string", "example": "user_12345"},
                "email": {"type": "string", "format": "email"},
                "phone": {"type": "string"},
                "address_line": {"type": "string"},
                "city": {"type": "string"},
            },
        },
        "ApplicantCreateDocument": {
            "type": "object",
            "required": ["country", "identity_source"],
            "properties": {
                "identity_source": {"type": "string", "enum": ["document"]},
                "country": {"type": "string", "example": "NG"},
                "external_ref": {"type": "string", "example": "user_12345"},
                "email": {"type": "string", "format": "email"},
                "phone": {"type": "string"},
                "address_line": {"type": "string"},
                "city": {"type": "string"},
            },
        },
        "SessionCreate": {
            "description": "Create a session in exactly one of three ways: for an existing applicant, inline as a "
                           "document-sourced session, or from a verified reusable credential.",
            "oneOf": [
                {
                    "type": "object",
                    "required": ["applicant_id", "level"],
                    "properties": {
                        "applicant_id": {"type": "string", "format": "uuid"},
                        "level": {"type": "integer", "enum": [1, 2, 3]},
                        "expires_hours": {"type": "integer", "minimum": 1, "default": 24},
                    },
                },
                {
                    "type": "object",
                    "required": ["identity_source", "country", "level"],
                    "properties": {
                        "identity_source": {"type": "string", "enum": ["document"]},
                        "country": {"type": "string", "example": "NG"},
                        "external_ref": {"type": "string"},
                        "level": {"type": "integer", "enum": [1, 2, 3]},
                        "expires_hours": {"type": "integer", "minimum": 1, "default": 24},
                    },
                },
                {
                    "type": "object",
                    "required": ["credential", "level"],
                    "properties": {
                        "credential": ref("Credential"),
                        "level": {"type": "integer", "enum": [1, 2, 3]},
                        "expires_hours": {"type": "integer", "minimum": 1, "default": 24},
                    },
                },
            ],
        },
        "SessionCreated": {
            "type": "object",
            "required": ["id", "level", "env", "status", "applicant_id", "flow_url", "flow_token", "expires_at"],
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "level": {"type": "integer", "enum": [1, 2, 3]},
                "env": ref("Environment"),
                "status": ref("SessionStatus"),
                "applicant_id": {"type": "string", "format": "uuid"},
                "identity_source": ref("IdentitySource"),
                "flow_url": {"type": "string", "example": "/flow/REPLACE_WITH_TOKEN",
                               "description": "Path on the KYC host. Prepend https://kyc.novamail.store in production."},
                "flow_token": {"type": "string", "description": "Sensitive one-session token. Do not log it or expose it to another user."},
                "expires_at": {"type": "string", "format": "date-time"},
                "credential_id": {"type": ["string", "null"], "format": "uuid"},
                "inherited_checks": {"type": "array", "items": {"type": "string"}},
            },
        },
        "Decision": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "session_id": {"type": "string", "format": "uuid"},
                "tenant_id": {"type": "string", "format": "uuid"},
                "env": ref("Environment"),
                "outcome": {"type": "string", "enum": ["approved", "rejected", "needs_review", "needs_more_information"]},
                "decided_by": {"type": "string", "example": "engine"},
                "reason": {"type": ["string", "null"]},
                "reason_codes": {"type": "array", "items": {"type": "string"}},
                "rules_version": {"type": "string"},
                "risk_score": {"type": ["number", "null"]},
                "risk_band": {"type": ["string", "null"], "enum": ["low", "medium", "high", None]},
                "risk_contributions": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "config_version": {"type": ["integer", "string", "null"]},
                "created_at": {"type": "string", "format": "date-time"},
            },
            "additionalProperties": True,
        },
        "Session": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "tenant_id": {"type": "string", "format": "uuid"},
                "env": ref("Environment"),
                "applicant_id": {"type": "string", "format": "uuid"},
                "identity_source": ref("IdentitySource"),
                "level": {"type": "integer", "enum": [1, 2, 3]},
                "status": ref("SessionStatus"),
                "expires_at": {"type": "string", "format": "date-time"},
                "created_at": {"type": "string", "format": "date-time"},
                "client_ip_masked": {"type": ["string", "null"]},
                "ip_country": {"type": ["string", "null"]},
                "vpn_status": {"type": ["string", "null"]},
                "checks_summary": {"type": "object", "additionalProperties": ref("CheckStatus")},
                "decision": {"oneOf": [ref("Decision"), {"type": "null"}]},
                "credential": ref("Credential"),
                "case_id": {"type": "string", "format": "uuid"},
            },
            "additionalProperties": True,
        },
        "Check": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "session_id": {"type": "string", "format": "uuid"},
                "tenant_id": {"type": "string", "format": "uuid"},
                "env": ref("Environment"),
                "type": {"type": "string", "example": "face_match"},
                "provider": {"type": ["string", "null"]},
                "status": ref("CheckStatus"),
                "findings": {"type": "object", "additionalProperties": True},
                "reason_codes": {"type": "array", "items": {"type": "string"}},
                "created_at": {"type": "string", "format": "date-time"},
            },
            "additionalProperties": True,
        },
        "Credential": {
            "type": "object",
            "description": "A signed reusable verification credential. It carries claims only, never document images "
                           "or biometric data.",
            "properties": {
                "claims": {"type": "object", "additionalProperties": True},
                "signature": {"type": "string"},
            },
            "additionalProperties": True,
        },
    },
}

COMPONENTS["schemas"].update({
    "FlowConfig": {
        "type": "object",
        "required": ["required_checks", "face_pass_threshold", "face_margin",
                     "risk_auto_approve_ceiling", "poa_window_days", "screening_threshold",
                     "sla_hours", "four_eyes"],
        "properties": {
            "required_checks": {"type": "array", "items": {"type": "string"}},
            "face_pass_threshold": {"type": "number", "minimum": 0, "maximum": 1},
            "face_margin": {"type": "number", "minimum": 0, "maximum": 1},
            "risk_auto_approve_ceiling": {"type": "number", "minimum": -1, "maximum": 100},
            "poa_window_days": {"type": "integer", "minimum": 1},
            "screening_threshold": {"type": "number", "minimum": 0, "maximum": 100},
            "sla_hours": {"type": "integer", "minimum": 1},
            "four_eyes": {"type": "boolean"},
        },
    },
    "FlowConfigPatch": {
        "type": "object",
        "minProperties": 1,
        "description": "Partial configuration. Unknown keys and out-of-range values are rejected with 422.",
        "properties": {
            "required_checks": {"type": "array", "minItems": 1, "items": {"type": "string"}},
            "face_pass_threshold": {"type": "number", "minimum": 0, "maximum": 1},
            "face_margin": {"type": "number", "minimum": 0, "maximum": 1},
            "risk_auto_approve_ceiling": {"type": "number", "minimum": -1, "maximum": 100},
            "poa_window_days": {"type": "integer", "minimum": 1},
            "screening_threshold": {"type": "number", "minimum": 0, "maximum": 100},
            "sla_hours": {"type": "integer", "minimum": 1},
            "four_eyes": {"type": "boolean"},
        },
    },
    "WebhookCreate": {
        "type": "object",
        "required": ["url"],
        "properties": {
            "url": {"type": "string", "format": "uri", "example": "https://api.example.com/webhooks/nova-kyc",
                    "description": "Public HTTP(S) receiver. Private, loopback, link-local and reserved targets are refused at delivery by the SSRF guard."},
            "events": {
                "type": "array",
                "description": "Implemented event names. An empty list subscribes to every event.",
                "items": {"type": "string", "enum": ["session.completed", "case.opened", "case.decided",
                                                       "applicant.deleted", "screening.hit_new"]},
            },
        },
    },
    "WebhookCreated": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "format": "uuid"},
            "url": {"type": "string", "format": "uri"},
            "secret": {"type": "string", "description": "Shown once. Store it in a secret manager."},
            "note": {"type": "string"},
        },
    },
    "WebhookEndpoint": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "format": "uuid"},
            "url": {"type": "string", "format": "uri"},
            "events": {"type": "array", "items": {"type": "string"}},
            "created_at": {"type": "string", "format": "date-time"},
        },
        "additionalProperties": True,
    },
    "WebhookDelivery": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "format": "uuid"},
            "endpoint_id": {"type": "string", "format": "uuid"},
            "tenant_id": {"type": "string", "format": "uuid"},
            "event": {"type": "string"},
            "payload": {"type": "string", "description": "The exact JSON body that was signed and delivered."},
            "signature": {"type": "string"},
            "status": {"type": "string", "enum": ["pending", "delivered", "failed", "dead_letter"]},
            "attempts": {"type": "integer"},
            "response_summary": {"type": ["string", "null"]},
            "next_attempt_at": {"type": ["string", "null"], "format": "date-time"},
            "dead_lettered_at": {"type": ["string", "null"], "format": "date-time"},
            "created_at": {"type": "string", "format": "date-time"},
        },
        "additionalProperties": True,
    },
    "WebhookEvent": {
        "type": "object",
        "required": ["event", "data"],
        "properties": {
            "event": {"type": "string", "enum": ["session.completed", "case.opened", "case.decided",
                                                  "applicant.deleted", "screening.hit_new"]},
            "data": {"type": "object", "additionalProperties": True,
                     "description": "Event-specific decision data. It never contains document images or raw biometric data."},
        },
    },
    "TenantUserCreate": {
        "type": "object",
        "required": ["name", "role"],
        "properties": {
            "name": {"type": "string"},
            "role": {"type": "string", "enum": ["admin", "reviewer"]},
        },
    },
    "TenantUser": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "format": "uuid"},
            "name": {"type": "string"},
            "role": {"type": "string", "enum": ["admin", "reviewer"]},
            "token_prefix": {"type": "string"},
            "created_at": {"type": "string", "format": "date-time"},
            "revoked_at": {"type": ["string", "null"], "format": "date-time"},
        },
        "additionalProperties": True,
    },
    "BusinessCreate": {
        "type": "object",
        "required": ["legal_name", "registration_number", "country"],
        "properties": {
            "legal_name": {"type": "string"},
            "registration_number": {"type": "string"},
            "country": {"type": "string", "description": "Country with a registration-number format in the platform registry."},
        },
    },
    "BusinessPersonCreate": {
        "type": "object",
        "required": ["applicant_id", "role"],
        "properties": {
            "applicant_id": {"type": "string", "format": "uuid"},
            "role": {"type": "string", "enum": ["director", "ubo"]},
            "ownership_pct": {"type": ["number", "null"], "minimum": 0, "maximum": 100},
        },
    },
    "Business": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "format": "uuid"},
            "tenant_id": {"type": "string", "format": "uuid"},
            "env": ref("Environment"),
            "legal_name": {"type": "string"},
            "registration_number": {"type": "string"},
            "country": {"type": "string"},
            "status": {"type": "string", "enum": ["pending", "verified", "rejected"]},
            "registry_status": {"type": "string"},
            "registry_source": {"type": ["string", "null"]},
            "registry_checked_at": {"type": ["string", "null"], "format": "date-time"},
            "registry_lookup_status": {"type": ["string", "null"]},
            "people": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            "documents": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            "screening_hits": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            "created_at": {"type": "string", "format": "date-time"},
            "updated_at": {"type": "string", "format": "date-time"},
        },
        "additionalProperties": True,
    },
    "CaseDecision": {
        "type": "object",
        "required": ["action", "reason"],
        "properties": {
            "action": {"type": "string", "enum": ["approve", "reject", "request_more"]},
            "reason": {"type": "string", "minLength": 1},
        },
    },
    "CaseConfirm": {
        "type": "object",
        "required": ["reason"],
        "properties": {"reason": {"type": "string", "minLength": 1}},
    },
    "HitDisposition": {
        "type": "object",
        "required": ["disposition", "reason"],
        "properties": {
            "disposition": {"type": "string", "enum": ["confirmed", "false_positive"]},
            "reason": {"type": "string", "minLength": 1},
        },
    },
    "CredentialVerifyRequest": {
        "type": "object",
        "required": ["credential"],
        "properties": {"credential": ref("Credential")},
    },
    "CredentialVerifyResponse": {
        "type": "object",
        "required": ["valid"],
        "properties": {
            "valid": {"type": "boolean"},
            "reason": {"type": "string"},
            "claims": {"type": "object", "additionalProperties": True},
        },
    },
    "FlowConsent": {
        "type": "object",
        "properties": {
            "text_version": {"type": "string"},
            "locale": {"type": "string", "example": "en"},
            "device_tz": {"type": "string", "example": "Africa/Lagos",
                          "description": "IANA timezone reported by the applicant device; used only as a corroborating location signal."},
            "webrtc_ips": {"type": "array", "items": {"type": "string"},
                           "description": "WebRTC candidate addresses reported by the flow for the VPN/proxy assessment."},
        },
    },
    "FlowSession": {
        "type": "object",
        "properties": {
            "session": {"type": "object", "additionalProperties": True},
            "applicant": ref("Applicant"),
            "documents": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            "document_registry": {"type": "object", "additionalProperties": True,
                                  "description": "Authoritative per-country document facts used by the flow, including label, side count, expiry behaviour and machine-readable-zone location."},
            "selfie_uploaded": {"type": "boolean"},
            "liveness_uploaded": {"type": "boolean"},
            "liveness_challenge": {"type": ["object", "null"], "additionalProperties": True},
            "poa_uploaded": {"type": "boolean"},
            "credential_issued": {"type": "boolean"},
            "allowed_docs": {"type": "object", "additionalProperties": {"type": "array", "items": {"type": "string"}}},
            "consent_text_version": {"type": "string"},
        },
    },
    "DocumentRead": {
        "type": "object",
        "properties": {
            "document_id": {"type": "string", "format": "uuid"},
            "document_label": {"type": "string"},
            "framing": {"type": "object", "additionalProperties": True},
            "read": {
                "type": "object",
                "properties": {
                    "first_name": {"type": ["string", "null"]},
                    "last_name": {"type": ["string", "null"]},
                    "dob": {"type": ["string", "null"]},
                    "number": {"type": ["string", "null"]},
                    "expiry": {"type": ["string", "null"]},
                },
                "additionalProperties": True,
            },
            "missing": {"type": "array", "items": {"type": "string"}},
            "complete": {"type": "boolean"},
            "quality": {"type": "object", "additionalProperties": True},
            "cross_engine": {"type": "object", "additionalProperties": True},
        },
        "additionalProperties": True,
    },
    "ProcessingAccepted": {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["processing", "reading"]},
            "session_id": {"type": "string", "format": "uuid"},
            "document_id": {"type": "string", "format": "uuid"},
        },
    },
})

COMPONENTS["schemas"].update({
    "TenantCreate": {
        "type": "object", "required": ["name"],
        "properties": {"name": {"type": "string"}, "country": {"type": "string"}},
    },
    "TenantCreated": {
        "type": "object",
        "properties": {
            "tenant": {"type": "object", "properties": {"id": {"type": "string", "format": "uuid"}, "name": {"type": "string"}}},
            "keys": {"type": "object", "additionalProperties": {"type": "object", "additionalProperties": True}},
        },
    },
    "PlatformPriceCreate": {
        "type": "object", "required": ["level", "env", "unit_price_cents"],
        "properties": {
            "level": {"type": "integer", "enum": [1, 2, 3]},
            "env": ref("Environment"),
            "unit_price_cents": {"type": "integer", "minimum": 0},
            "currency": {"type": "string", "default": "USD"},
            "tenant_id": {"type": "string", "format": "uuid"},
        },
    },
    "PlatformQuotaCreate": {
        "type": "object", "required": ["tenant_id", "monthly_limit"],
        "properties": {"tenant_id": {"type": "string", "format": "uuid"}, "monthly_limit": {"type": "integer", "minimum": 0}},
    },
    "PlatformInvoiceCreate": {
        "type": "object", "required": ["tenant_id", "period_start", "period_end"],
        "properties": {
            "tenant_id": {"type": "string", "format": "uuid"},
            "env": ref("Environment"),
            "period_start": {"type": "string", "format": "date-time"},
            "period_end": {"type": "string", "format": "date-time"},
        },
    },
    "MfaCode": {
        "type": "object", "required": ["code"],
        "properties": {"code": {"type": "string", "pattern": "^[0-9]{6}$"}},
    },
    "RegistryDecision": {
        "type": "object", "required": ["status", "reason"],
        "properties": {
            "status": {"type": "string", "enum": ["confirmed", "rejected"]},
            "reason": {"type": "string", "minLength": 1},
        },
    },
})

OPS = []


def add(method, path, *args, **kwargs):
    OPS.append((method, path, operation(*args, **kwargs)))


def wrapper(property_name, item_schema):
    return {"type": "object", "properties": {property_name: item_schema}}


# Developer resources and health
add("get", "/docs", "getDeveloperDocumentation", "Developer resources",
    "Open the human developer documentation portal. It links the integration guide, API reference, JavaScript SDK, "
    "and downloadable OpenAPI documents.", NONE, 200,
    {"type": "string", "format": "html"}, "Developer documentation portal", errors=(), content_type="text/html")
add("get", "/openapi.json", "getOpenApiJson", "Developer resources",
    "Download the machine-readable OpenAPI 3.1 specification as JSON. Import it into Postman, Insomnia, "
    "openapi-generator, or an AI agent's tool registry.", NONE, 200,
    {"type": "object", "additionalProperties": True}, "OpenAPI specification (JSON)", errors=())
add("get", "/openapi.yaml", "getOpenApiYaml", "Developer resources",
    "Download the same OpenAPI 3.1 specification as YAML.", NONE, 200,
    {"type": "string"}, "OpenAPI specification (YAML)", errors=(), content_type="application/yaml")
add("get", "/healthz", "getHealth", "Health",
    "Capability-aware health. A 200 means the HTTP service and its critical OCR capability are available; "
    "a deployment whose OCR binary is missing answers 503 instead of pretending to be healthy.", NONE, 200,
    {"type": "object", "properties": {"ok": {"type": "boolean"},
                                      "missing": {"type": "array", "items": {"type": "string"}}}},
    "Service is healthy", errors=(503,))

# Platform operations
add("post", "/v1/tenants", "createTenant", "Platform operations",
    "Create a tenant and its test and live API keys. This is an operator operation, not public self-service signup. "
    "Both raw keys are shown once in the response.", PLATFORM, 201, ref("TenantCreated"), "Tenant created",
    request_body=body(ref("TenantCreate"), examples={"create": {"value": {"name": "Example Ltd", "country": "NG"}}}),
    errors=(403, 422, 429))
add("delete", "/v1/platform/tenants/{tenantId}", "deleteTenant", "Platform operations",
    "Delete a tenant's operational data and stored media while retaining audit, deletion, invoice and usage records. "
    "The JSON body must repeat the tenant id as an explicit confirmation.", PLATFORM, 200,
    {"type": "object", "additionalProperties": True}, "Tenant deleted",
    parameters=[PARAMS["tenantId"]],
    request_body=body({"type": "object", "required": ["confirm"],
                       "properties": {"confirm": {"type": "string", "format": "uuid"}}}),
    errors=(403, 404, 422, 429))
add("get", "/v1/platform/metrics", "getPlatformMetrics", "Platform operations",
    "Read 24-hour session and decision counts, current processing depth, webhook dead-letter count and fraud-index size.",
    PLATFORM, 200, {"type": "object", "additionalProperties": True}, "Platform metrics", errors=(403, 429))
add("post", "/v1/platform/prices", "setPlatformPrice", "Platform operations",
    "Set the versioned unit price for a verification level and environment. Documentation does not publish a price; "
    "prices are operator configuration.", PLATFORM, 201,
    {"type": "object", "properties": {"price_id": {"type": "string", "format": "uuid"}}}, "Price set",
    request_body=body(ref("PlatformPriceCreate")), errors=(403, 422, 429))
add("post", "/v1/platform/quotas", "setPlatformQuota", "Platform operations",
    "Set a tenant's monthly live-verification quota. Test verifications are not capped by this quota.",
    PLATFORM, 200, {"type": "object", "properties": {"tenant_id": {"type": "string", "format": "uuid"},
                                                      "monthly_limit": {"type": "integer"}}}, "Quota set",
    request_body=body(ref("PlatformQuotaCreate")), errors=(403, 422, 429))
add("post", "/v1/platform/invoices", "generatePlatformInvoice", "Platform operations",
    "Generate a draft invoice from priced, uninvoiced usage in a period.", PLATFORM, 201,
    {"type": "object", "additionalProperties": True}, "Invoice generated or no priced usage found",
    request_body=body(ref("PlatformInvoiceCreate")), errors=(403, 422, 429))

# Applicants and sessions
add("post", "/v1/applicants", "createApplicant", "Applicants",
    "Create an applicant. Prefer identity_source=document: the platform reads the identity from the document and "
    "adopts it after decision. The declared form cross-checks a name and date of birth the tenant already holds.",
    TENANT, 201, ref("Applicant"), "Applicant created",
    request_body=body(ref("ApplicantCreate"), examples={
        "documentIdentity": {"summary": "Recommended: identity read from the document",
                             "value": {"country": "NG", "identity_source": "document", "external_ref": "user_12345"}},
        "declaredIdentity": {"summary": "Cross-check an identity the tenant already holds",
                             "value": {"country": "NG", "first_name": "Adaeze", "last_name": "Example",
                                       "dob": "1992-04-17", "external_ref": "user_12345"}},
    }), errors=(401, 422, 429))
add("get", "/v1/applicants/{applicantId}", "getApplicant", "Applicants",
    "Read one applicant owned by the authenticated tenant and environment. The view is audited.",
    TENANT, 200, ref("Applicant"), "Applicant", parameters=[PARAMS["applicantId"]], errors=(401, 404, 429))
add("delete", "/v1/applicants/{applicantId}", "eraseApplicant", "Applicants",
    "Perform subject erasure: stored document and biometric files are deleted, direct PII fields are nulled, "
    "the erasure is audited, and applicant.deleted is emitted to matching webhooks.",
    TENANT, 200, {"type": "object", "properties": {"deleted": {"type": "boolean"},
                                                    "applicant_id": {"type": "string", "format": "uuid"},
                                                    "files_deleted": {"type": "integer"}}},
    "Applicant erased", parameters=[PARAMS["applicantId"]], errors=(401, 404, 429))
add("post", "/v1/sessions", "createSession", "Sessions",
    "Create a verification session and receive its hosted-flow URL and one-session flow token. Level 1 is the "
    "document-identity core; Level 2 adds the full biometric and authenticity set; Level 3 adds proof of address "
    "and sanctions screening under the tenant's active configuration.",
    TENANT, 201, ref("SessionCreated"), "Session created",
    request_body=body(ref("SessionCreate"), examples={
        "existingApplicant": {"value": {"applicant_id": "00000000-0000-4000-8000-000000000001", "level": 2}},
        "documentSession": {"value": {"identity_source": "document", "country": "NG", "level": 1,
                                       "external_ref": "user_12345"}},
    }), errors=(401, 404, 422, 429))
add("get", "/v1/sessions", "listSessions", "Sessions",
    "List sessions for the authenticated tenant and environment, newest first.",
    TENANT, 200, wrapper("sessions", array_of("Session")), "Sessions", errors=(401, 429))
add("get", "/v1/sessions/{sessionId}", "getSession", "Sessions",
    "Read a session's status, check summary, decision, masked client IP, IP country and VPN status.",
    TENANT, 200, ref("Session"), "Session", parameters=[PARAMS["sessionId"]], errors=(401, 404, 429))
add("get", "/v1/sessions/{sessionId}/checks", "listSessionChecks", "Sessions",
    "Read every recorded check for a session, including provider, findings and reason codes.",
    TENANT, 200, wrapper("checks", array_of("Check")), "Session checks",
    parameters=[PARAMS["sessionId"]], errors=(401, 404, 429))
add("post", "/v1/sessions/{sessionId}/cancel", "cancelSession", "Sessions",
    "Cancel a live session. Its hosted-flow token stops working immediately.",
    TENANT, 200, {"type": "object", "properties": {"cancelled": {"type": "boolean"}}}, "Session cancelled",
    parameters=[PARAMS["sessionId"]], errors=(401, 404, 429))
add("get", "/v1/sessions/{sessionId}/credential", "getSessionCredential", "Credentials",
    "Read the reusable credential issued for an approved session. Claims and signature only.",
    TENANT, 200, {"type": "object", "properties": {"credential": ref("Credential"), "status": {"type": "string"}}},
    "Issued credential", parameters=[PARAMS["sessionId"]], errors=(401, 404, 429))

# Configuration, keys, users, webhooks, credentials, monitoring
add("get", "/v1/config", "getFlowConfig", "Configuration",
    "Read the active flow configuration for a level. If the tenant has never stored a version, the platform defaults "
    "and version 0 are returned.", TENANT, 200,
    {"type": "object", "properties": {"level": {"type": "integer"}, "version": {"type": "integer"},
                                      "config": ref("FlowConfig")}}, "Active flow configuration",
    parameters=[query_param("level", "Verification level.", {"type": "integer", "enum": [1, 2, 3], "default": 2})],
    errors=(401, 422, 429))
add("put", "/v1/config", "updateFlowConfig", "Configuration",
    "Store a new version of a level's flow configuration. The request body is {level, config:{...patch}}; "
    "the SDK's updateConfig method builds this shape for you.", TENANT, 200,
    {"type": "object", "properties": {"level": {"type": "integer"}, "version": {"type": "integer"},
                                      "config": ref("FlowConfig")}}, "Updated flow configuration",
    request_body=body({"type": "object", "required": ["level", "config"],
                       "properties": {"level": {"type": "integer", "enum": [1, 2, 3]},
                                      "config": ref("FlowConfigPatch")}},
                      examples={"tighten": {"value": {"level": 2, "config": {"four_eyes": True, "sla_hours": 12}}}}),
    errors=(401, 422, 429))
add("get", "/v1/keys", "listApiKeys", "Keys",
    "List the tenant's API keys across environments without exposing key material. Only prefixes and lifecycle fields are returned.",
    TENANT, 200, wrapper("keys", {"type": "array", "items": {"type": "object", "additionalProperties": True}}),
    "API keys", errors=(401, 429))
add("post", "/v1/keys/{keyId}/revoke", "revokeApiKey", "Keys",
    "Revoke one of the tenant's API keys immediately.", TENANT, 200,
    {"type": "object", "properties": {"revoked": {"type": "boolean"}}}, "API key revoked",
    parameters=[PARAMS["keyId"]], errors=(401, 404, 429))
add("post", "/v1/users", "createTenantUser", "Users and reviewer MFA",
    "Create a named tenant user. The returned token is shown once and is presented as X-Reviewer-Key on reviewer actions.",
    TENANT, 201, {"type": "object", "additionalProperties": True}, "Tenant user created",
    request_body=body(ref("TenantUserCreate")), errors=(401, 422, 429))
add("get", "/v1/users", "listTenantUsers", "Users and reviewer MFA",
    "List named tenant users without token material.", TENANT, 200,
    wrapper("users", array_of("TenantUser")), "Tenant users", errors=(401, 429))
add("post", "/v1/users/{userId}/revoke", "revokeTenantUser", "Users and reviewer MFA",
    "Revoke a named tenant user's token.", TENANT, 200,
    {"type": "object", "properties": {"revoked": {"type": "boolean"}}}, "Tenant user revoked",
    parameters=[PARAMS["userId"]], errors=(401, 404, 429))
add("post", "/v1/users/{userId}/mfa/enroll", "enrollReviewerMfa", "Users and reviewer MFA",
    "Start TOTP MFA enrolment for a named user. The secret and otpauth URI are shown once; MFA activates only after confirmation.",
    TENANT, 200, {"type": "object", "additionalProperties": True}, "MFA enrolment started",
    parameters=[PARAMS["userId"]], errors=(401, 404, 409, 429))
add("post", "/v1/users/{userId}/mfa/confirm", "confirmReviewerMfa", "Users and reviewer MFA",
    "Confirm TOTP MFA enrolment with a current six-digit code.", TENANT, 200,
    {"type": "object", "additionalProperties": True}, "MFA enabled",
    parameters=[PARAMS["userId"]], request_body=body(ref("MfaCode")), errors=(401, 404, 409, 429))
add("post", "/v1/users/{userId}/mfa/reset", "resetReviewerMfa", "Users and reviewer MFA",
    "Tenant-admin recovery: clear a user's MFA secret and disable MFA. The user must re-enrol; no bypass code is issued.",
    TENANT, 200, {"type": "object", "additionalProperties": True}, "MFA reset",
    parameters=[PARAMS["userId"]], errors=(401, 404, 429))
add("post", "/v1/webhooks", "createWebhookEndpoint", "Webhooks",
    "Register a webhook endpoint for the authenticated tenant and environment. The signing secret is shown once. "
    "An empty events list receives every implemented event.", TENANT, 201, ref("WebhookCreated"), "Webhook endpoint created",
    request_body=body(ref("WebhookCreate"), examples={"sessionEvents": {"value": {
        "url": "https://api.example.com/webhooks/nova-kyc",
        "events": ["session.completed", "case.opened", "case.decided"]}}}),
    errors=(401, 422, 429))
add("get", "/v1/webhooks", "listWebhookEndpoints", "Webhooks",
    "List webhook endpoints for the authenticated tenant and environment. Secrets are never returned.",
    TENANT, 200, wrapper("endpoints", array_of("WebhookEndpoint")), "Webhook endpoints", errors=(401, 429))
add("delete", "/v1/webhooks/{webhookId}", "deleteWebhookEndpoint", "Webhooks",
    "Delete one of the tenant's webhook endpoints and its delivery records.",
    TENANT, 200, {"type": "object", "properties": {"deleted": {"type": "string", "format": "uuid"},
                                                    "deliveries_removed": {"type": "integer"}}},
    "Webhook endpoint deleted", parameters=[PARAMS["webhookId"]], errors=(401, 404, 429))
add("get", "/v1/webhooks/deliveries", "listWebhookDeliveries", "Webhooks",
    "List up to 200 recent webhook deliveries for the tenant and environment, optionally filtered by status.",
    TENANT, 200, wrapper("deliveries", array_of("WebhookDelivery")), "Webhook deliveries",
    parameters=[query_param("status", "Delivery status filter.",
                            {"type": "string", "enum": ["pending", "delivered", "failed", "dead_letter"]})],
    errors=(401, 422, 429))
add("post", "/v1/webhooks/deliveries/{deliveryId}/replay", "replayWebhookDelivery", "Webhooks",
    "Reset a failed or dead-lettered delivery's attempt budget and deliver it immediately with a fresh signature.",
    TENANT, 200, wrapper("delivery", ref("WebhookDelivery")), "Delivery replayed",
    parameters=[PARAMS["deliveryId"]], errors=(401, 404, 409, 429))
add("post", "/v1/credentials/verify", "verifyCredential", "Credentials",
    "Verify a reusable credential's signature, status and expiry. Any tenant key may verify. The response contains "
    "claims only, never document data.", TENANT, 200, ref("CredentialVerifyResponse"), "Credential verification result",
    request_body=body(ref("CredentialVerifyRequest")), errors=(401, 422, 429))
add("post", "/v1/credentials/revoke", "revokeCredential", "Credentials",
    "Revoke a credential issued by the authenticated tenant and environment.",
    TENANT, 200, {"type": "object", "properties": {"revoked": {"type": "boolean"},
                                                    "credential_id": {"type": "string", "format": "uuid"}}},
    "Credential revoked",
    request_body=body({"type": "object", "required": ["credential_id"],
                       "properties": {"credential_id": {"type": "string", "format": "uuid"}}}),
    errors=(401, 404, 422, 429))
add("post", "/v1/monitoring/rescreen", "rescreenApplicants", "Monitoring",
    "Re-screen all approved applicants of the tenant against the current screening lists using the Level 3 threshold. "
    "New matches create alerts, emit screening.hit_new and reopen cases; monitoring never silently un-approves a person.",
    TENANT, 200, {"type": "object", "additionalProperties": True}, "Rescreening result", errors=(401, 429))
add("get", "/v1/monitoring/alerts", "listMonitoringAlerts", "Monitoring",
    "List ongoing-monitoring alerts for the authenticated tenant and environment.",
    TENANT, 200, wrapper("alerts", {"type": "array", "items": {"type": "object", "additionalProperties": True}}),
    "Monitoring alerts", errors=(401, 429))
add("get", "/v1/usage", "getUsage", "Billing and usage",
    "Read metered usage for a period. The default period is the current UTC month. Every decided session is metered "
    "exactly once; test-environment events are priced at zero in the sandbox model.",
    TENANT, 200, {"type": "object", "additionalProperties": True}, "Usage summary",
    parameters=[query_param("from", "Inclusive ISO-8601 period start."), query_param("to", "Inclusive ISO-8601 period end.")],
    errors=(401, 422, 429))
add("get", "/v1/invoices", "listInvoices", "Billing and usage",
    "List generated invoices for the authenticated tenant and environment.",
    TENANT, 200, wrapper("invoices", {"type": "array", "items": {"type": "object", "additionalProperties": True}}),
    "Invoices", errors=(401, 429))

# Businesses, cases, and protected media
add("post", "/v1/businesses", "createBusiness", "Businesses (KYB)",
    "Create a KYB business. The registration number is format-validated for its country; format validation alone "
    "is not represented as a live government-registry verification.", TENANT, 201, ref("Business"), "Business created",
    request_body=body(ref("BusinessCreate")), errors=(401, 422, 429))
add("get", "/v1/businesses", "listBusinesses", "Businesses (KYB)",
    "List businesses for the authenticated tenant and environment with brief people summaries.",
    TENANT, 200, wrapper("businesses", array_of("Business")), "Businesses", errors=(401, 429))
add("get", "/v1/businesses/{businessId}", "getBusiness", "Businesses (KYB)",
    "Read one business with its people, documents and screening hits.", TENANT, 200, ref("Business"), "Business",
    parameters=[PARAMS["businessId"]], errors=(401, 404, 429))
add("post", "/v1/businesses/{businessId}/people", "addBusinessPerson", "Businesses (KYB)",
    "Attach an applicant to a business as a director or ultimate beneficial owner. The API schema currently accepts "
    "director or ubo; an officer role is not accepted by this endpoint.", TENANT, 201, ref("Business"), "Person attached",
    parameters=[PARAMS["businessId"]], request_body=body(ref("BusinessPersonCreate")), errors=(401, 404, 409, 422, 429))
add("post", "/v1/businesses/{businessId}/document", "uploadBusinessDocument", "Businesses (KYB)",
    "Upload company registry evidence as multipart form data. The document is stored encrypted under the platform's "
    "storage controls and is not returned as a public URL.", TENANT, 201,
    {"type": "object", "properties": {"document_id": {"type": "string", "format": "uuid"},
                                       "registry_status": {"type": "string"}}}, "Business document uploaded",
    parameters=[PARAMS["businessId"]],
    request_body=form_body({"type": "object", "required": ["document"],
                            "properties": {"document": {"type": "string", "format": "binary"},
                                           "kind": {"type": "string", "default": "registration"}}}),
    errors=(401, 404, 413, 422, 429))
add("post", "/v1/businesses/{businessId}/registry-check", "checkBusinessRegistry", "Businesses (KYB)",
    "Consult the authoritative registry adapter configured for the business's country and store the lookup outcome. "
    "Adapters fail closed: where a source is not configured, the result says not_configured rather than guessing.",
    TENANT, 200, {"type": "object", "properties": {"business_id": {"type": "string", "format": "uuid"},
                                                     "registry_lookup": {"type": "object", "additionalProperties": True}}},
    "Registry lookup result", parameters=[PARAMS["businessId"]], errors=(401, 404, 429))
add("post", "/v1/businesses/{businessId}/registry", "decideBusinessRegistry", "Businesses (KYB)",
    "Record a reviewer's registry decision after examining the format validation, uploaded evidence and any adapter "
    "lookup. A reason is mandatory. This endpoint does not pretend that a human confirmation is itself a live registry connection.",
    TENANT, 200, {"type": "object", "additionalProperties": True}, "Registry decision recorded",
    parameters=[PARAMS["businessId"]] + REVIEWER_PARAMS, request_body=body(ref("RegistryDecision")),
    errors=(401, 403, 404, 422, 429))
add("post", "/v1/businesses/{businessId}/evaluate", "evaluateBusiness", "Businesses (KYB)",
    "Assemble the business decision. Verified requires a confirmed registry leg, at least one attached person, every "
    "person approved at Level 2 or above, and no pending or confirmed screening hit.", TENANT, 200,
    {"type": "object", "additionalProperties": True}, "Business evaluation",
    parameters=[PARAMS["businessId"]], errors=(401, 404, 429))
add("get", "/v1/cases", "listCases", "Review and cases",
    "List the tenant's review queue, sorted by SLA due time and then newest first.",
    TENANT, 200, wrapper("cases", {"type": "array", "items": {"type": "object", "additionalProperties": True}}),
    "Review cases", errors=(401, 429))
add("get", "/v1/cases/{caseId}", "getCase", "Review and cases",
    "Read the full audited case view: session, applicant, documents and biometric metadata, checks, screening hits, "
    "the deterministic human-assist summary and any issued credential. Image access uses the separate protected media endpoints.",
    TENANT, 200, {"type": "object", "additionalProperties": True}, "Review case",
    parameters=[PARAMS["caseId"]], errors=(401, 404, 429))
add("post", "/v1/cases/{caseId}/decide", "decideCase", "Review and cases",
    "Record a reviewer decision. A reason is mandatory. Privileged reviewer actions may require X-Reviewer-TOTP; "
    "some outcomes park the case for a different reviewer's four-eyes confirmation and return 202.",
    TENANT, 200, {"type": "object", "additionalProperties": True}, "Case decision recorded",
    parameters=[PARAMS["caseId"]] + REVIEWER_PARAMS, request_body=body(ref("CaseDecision")),
    errors=(401, 403, 404, 409, 422, 429),
    extra_responses={202: {"description": "Decision parked for four-eyes confirmation.",
                           "content": {"application/json": {"schema": {"type": "object", "additionalProperties": True}}}}})
add("post", "/v1/cases/{caseId}/confirm", "confirmCase", "Review and cases",
    "Confirm a parked case decision. The confirmer must be a different reviewer identity from the first decider.",
    TENANT, 200, {"type": "object", "additionalProperties": True}, "Case decision confirmed",
    parameters=[PARAMS["caseId"]] + REVIEWER_PARAMS, request_body=body(ref("CaseConfirm")),
    errors=(401, 403, 404, 409, 422, 429))
add("post", "/v1/cases/{caseId}/hits/{hitId}/dispose", "disposeScreeningHit", "Review and cases",
    "Dispose a screening hit as confirmed or false_positive with a mandatory reason. A confirmed hit rejects the "
    "session; a false-positive disposition lets the case proceed but flags it for four-eyes handling.",
    TENANT, 200, {"type": "object", "additionalProperties": True}, "Screening hit disposed",
    parameters=[PARAMS["caseId"], PARAMS["hitId"]] + REVIEWER_PARAMS,
    request_body=body(ref("HitDisposition")), errors=(401, 403, 404, 409, 422, 429))
add("get", "/v1/documents/{documentId}/image", "getDocumentImage", "Review and cases",
    "Download a stored document image for an authorized tenant reviewer. Use side=back for the back image. Every view "
    "is audited; this is not a public or signed URL.", TENANT, 200,
    {"type": "string", "format": "binary"}, "Document image",
    parameters=[PARAMS["documentId"], query_param("side", "Document side.", {"type": "string", "enum": ["front", "back"], "default": "front"})],
    errors=(401, 404, 429, 500, 503), content_type="image/jpeg")
add("get", "/v1/biometrics/{biometricId}/image", "getBiometricImage", "Review and cases",
    "Download a stored biometric capture image for an authorized tenant reviewer. Every view is audited; this is not "
    "a public or signed URL.", TENANT, 200, {"type": "string", "format": "binary"}, "Biometric image",
    parameters=[PARAMS["biometricId"]], errors=(401, 404, 429, 500, 503), content_type="image/jpeg")

# Hosted flow. These endpoints are intended for the platform's own hosted
# page and advanced native/web wrappers that preserve the flow-token model.
# They are not a general API-only capture substitute: the product's capture
# rules, live-camera requirements and NIN-slip exception are enforced here.
add("get", "/v1/flow/session", "getFlowSession", "Hosted flow",
    "Read the current hosted-flow state, applicant summary, already-uploaded capture metadata, the authoritative "
    "document registry and allowed documents for this session.", FLOW, 200, ref("FlowSession"), "Flow session state",
    errors=(401, 429))
add("get", "/v1/flow/credential", "getFlowCredential", "Hosted flow",
    "Read the applicant's own issued credential for this session, when one exists.", FLOW, 200,
    {"type": "object", "properties": {"credential": ref("Credential"), "status": {"type": "string"}}},
    "Issued credential", errors=(401, 404, 429))
add("post", "/v1/flow/consent", "submitFlowConsent", "Hosted flow",
    "Record consent, start the session, harvest the disclosed IP/location signals, and apply the VPN/proxy hard gate. "
    "A detected VPN or proxy returns 403 before scanning starts.", FLOW, 200,
    {"type": "object", "properties": {"consented": {"type": "boolean"}, "vpn_status": {"type": "string"}}},
    "Consent recorded", request_body=body(ref("FlowConsent"), required=False),
    errors=(401, 403, 422, 429))
add("post", "/v1/flow/document", "uploadFlowDocument", "Hosted flow",
    "Upload the document front and, when captured together, its back. The hosted flow normally sends live-camera "
    "frames. File upload is accepted by this endpoint for the flow's controlled cases; the Nigerian NIN slip is the "
    "named upload exception and is the only type that may carry a typed claimed_number.", FLOW, 201,
    {"type": "object", "properties": {"document_id": {"type": "string", "format": "uuid"},
                                       "kind": {"type": "string"}, "issuing_country": {"type": "string"},
                                       "sides": {"type": "integer"}, "has_expiry": {"type": "boolean"},
                                       "back_uploaded": {"type": "boolean"}}}, "Document stored",
    request_body=form_body({
        "type": "object", "required": ["kind", "issuing_country", "front"],
        "properties": {
            "kind": {"type": "string", "description": "Document kind from the session's document_registry."},
            "issuing_country": {"type": "string", "description": "ISO alpha-2 issuing country."},
            "front": {"type": "string", "format": "binary"},
            "back": {"type": "string", "format": "binary"},
            "capture_meta": {"type": "string", "description": "JSON string describing capture method and per-side metadata."},
            "claimed_number": {"type": "string", "description": "NIN slip only: the 11-digit number typed by the applicant. Rejected for every other document kind."},
        }}), errors=(401, 413, 422, 429))
add("post", "/v1/flow/document/back", "uploadFlowDocumentBack", "Hosted flow",
    "Attach the back side to an existing two-sided flow document.", FLOW, 201,
    {"type": "object", "properties": {"document_id": {"type": "string", "format": "uuid"}, "back_uploaded": {"type": "boolean"}}},
    "Document back stored",
    request_body=form_body({
        "type": "object", "required": ["document_id", "back"],
        "properties": {"document_id": {"type": "string", "format": "uuid"},
                       "back": {"type": "string", "format": "binary"},
                       "capture_meta": {"type": "string"}}}),
    errors=(401, 404, 413, 422, 429))
add("post", "/v1/flow/presence", "probeFlowPresence", "Hosted flow",
    "Check one live frame for a usable face and return coaching guidance. The frame is decoded in memory and is not stored.",
    FLOW, 200, {"type": "object", "properties": {"face_present": {"type": "boolean"},
                                                  "size_frac": {"type": "number"},
                                                  "centred": {"type": "boolean"},
                                                  "guidance": {"type": "string"},
                                                  "detail": {"type": "string"}}}, "Presence guidance",
    request_body=form_body({"type": "object", "required": ["frame"],
                            "properties": {"frame": {"type": "string", "format": "binary"}}}),
    errors=(401, 413, 422, 429))
add("post", "/v1/flow/selfie", "uploadFlowSelfie", "Hosted flow",
    "Upload the live selfie and optional same-second burst frames used by the continuous face track. The selfie part "
    "is required; burst_0 through burst_4 are optional.", FLOW, 201,
    {"type": "object", "properties": {"biometric_id": {"type": "string", "format": "uuid"}}}, "Selfie stored",
    request_body=form_body({
        "type": "object", "required": ["selfie"],
        "properties": {"selfie": {"type": "string", "format": "binary"},
                       "burst_0": {"type": "string", "format": "binary"},
                       "burst_1": {"type": "string", "format": "binary"},
                       "burst_2": {"type": "string", "format": "binary"},
                       "burst_3": {"type": "string", "format": "binary"},
                       "burst_4": {"type": "string", "format": "binary"},
                       "capture_meta": {"type": "string"}}}),
    errors=(401, 413, 422, 429))
add("post", "/v1/flow/liveness/challenge", "createFlowLivenessChallenge", "Hosted flow",
    "Issue a fresh server-generated movement challenge. The movement sequence comes from the server, never from the client.",
    FLOW, 201, {"type": "object", "properties": {"challenge": {"type": "object", "additionalProperties": True},
                                                  "instructions": {"type": "string"}}}, "Liveness challenge issued",
    errors=(401, 422, 429))
add("post", "/v1/flow/liveness", "uploadFlowLiveness", "Hosted flow",
    "Upload the active-liveness video for the previously issued challenge. WebM and MP4 filenames retain their media "
    "extension; other filenames are stored as binary media.", FLOW, 201,
    {"type": "object", "properties": {"biometric_id": {"type": "string", "format": "uuid"},
                                       "method": {"type": "string", "enum": ["active_challenge"]}}}, "Liveness video stored",
    request_body=form_body({"type": "object", "required": ["video"],
                            "properties": {"video": {"type": "string", "format": "binary"},
                                           "capture_meta": {"type": "string"}}}),
    errors=(401, 413, 422, 429))
add("post", "/v1/flow/poa", "uploadFlowPoa", "Hosted flow",
    "Upload the proof-of-address document for a Level 3 session.", FLOW, 201,
    {"type": "object", "properties": {"document_id": {"type": "string", "format": "uuid"},
                                       "kind": {"type": "string", "enum": ["proof_of_address"]}}}, "Proof of address stored",
    request_body=form_body({"type": "object", "required": ["document"],
                            "properties": {"document": {"type": "string", "format": "binary"},
                                           "capture_meta": {"type": "string"}}}),
    errors=(401, 413, 422, 429))
add("post", "/v1/flow/document/process", "processFlowDocument", "Hosted flow",
    "Read the uploaded document and return the server's read-back: extracted identity fields, missing required fields, "
    "framing, quality and cross-engine evidence. A long read returns 202 with status=reading; poll the same endpoint "
    "until it returns 200. A transport failure is never a document verdict.", FLOW, 200, ref("DocumentRead"),
    "Document read-back",
    request_body=body({"type": "object", "properties": {"document_id": {"type": "string", "format": "uuid"}}}, required=False),
    errors=(401, 404, 422, 429, 500),
    extra_responses={202: {"description": "The read is still running. Poll this endpoint.",
                           "content": {"application/json": {"schema": ref("ProcessingAccepted")}}}})
add("post", "/v1/flow/document/claim", "correctFlowDocumentClaim", "Hosted flow",
    "Correct the typed NIN for an already-uploaded Nigerian NIN slip without re-uploading it. The corrected claim is "
    "compared with the number read from the slip itself.", FLOW, 200,
    {"type": "object", "properties": {"claimed_number": {"type": "string"},
                                       "extracted_number": {"type": ["string", "null"]},
                                       "match": {"type": ["boolean", "null"]}}}, "NIN claim corrected",
    request_body=body({"type": "object", "required": ["document_id", "claimed_number"],
                       "properties": {"document_id": {"type": "string", "format": "uuid"},
                                      "claimed_number": {"type": "string", "pattern": "^[0-9]{11}$"}}}),
    errors=(401, 404, 422, 429))
add("post", "/v1/flow/submit", "submitFlowSession", "Hosted flow",
    "Submit the completed session for the automatic decision. If processing is already running or takes longer than "
    "the synchronous window, the endpoint returns 202 with status=processing; the tenant should read the session or "
    "wait for session.completed rather than submitting repeatedly.", FLOW, 200, ref("Session"), "Decision or final session view",
    errors=(401, 422, 429),
    extra_responses={202: {"description": "Decision processing is running.",
                           "content": {"application/json": {"schema": ref("ProcessingAccepted")}}}})
add("post", "/v1/flow/credential/revoke", "revokeFlowCredential", "Hosted flow",
    "Let the applicant revoke their own issued credential from the hosted flow.", FLOW, 200,
    {"type": "object", "properties": {"revoked": {"type": "boolean"},
                                       "credential_id": {"type": "string", "format": "uuid"}}}, "Credential revoked",
    request_body=body({"type": "object", "required": ["credential_id"],
                       "properties": {"credential_id": {"type": "string", "format": "uuid"}}}),
    errors=(401, 404, 422, 429))


def build_spec():
    paths = {}
    for method, path, op in OPS:
        paths.setdefault(path, {})[method] = op
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Nova KYC API",
            "version": "1.0.0",
            "summary": "Identity verification, KYB, review, credentials and monitoring for websites, mobile apps and backend systems.",
            "description": (
                "Nova KYC is a Nova Inc identity-verification platform. The recommended integration is deliberately "
                "simple: a server creates an applicant and a verification session, sends the person to the hosted "
                "phone-first flow, and learns the decision from a signed webhook or the Sessions API.\n\n"
                "Important boundaries:\n"
                "- API keys are server-side secrets. Never put one in a browser, mobile app, public repository or agent prompt.\n"
                "- The hosted flow is the capture product. There is no general API-only document/selfie upload endpoint.\n"
                "- The one upload exception is the Nigerian NIN slip inside the hosted flow.\n"
                "- Test and live keys select separate environments on the same production host.\n"
                "- Webhook payloads and reusable credentials carry claims and outcomes, never document images or raw biometric data.\n\n"
                "Human integration guide: https://kyc.novamail.store/docs\n"
                "Detailed developer guide: https://github.com/kilomene/KYC/blob/main/docs/DEVELOPER.md"
            ),
            "contact": {"name": "Nova Inc", "url": "https://kyc.novamail.store", "email": "info@novamail.store"},
        },
        "servers": [
            {"url": "https://kyc.novamail.store", "description": "Production (test and live environments are selected by API key)"},
            {"url": "http://127.0.0.1:8765", "description": "Local development default"},
        ],
        "tags": [
            {"name": "Developer resources", "description": "Documentation and machine-readable specifications."},
            {"name": "Health", "description": "Service capability health."},
            {"name": "Platform operations", "description": "Nova operator only; not tenant self-service."},
            {"name": "Applicants", "description": "People to be verified and privacy erasure."},
            {"name": "Sessions", "description": "Verification sessions, checks and outcomes."},
            {"name": "Hosted flow", "description": "The applicant-facing flow's token-scoped endpoints."},
            {"name": "Configuration", "description": "Versioned per-level decision configuration."},
            {"name": "Keys", "description": "Tenant API-key lifecycle metadata."},
            {"name": "Users and reviewer MFA", "description": "Named reviewers and TOTP enrolment."},
            {"name": "Webhooks", "description": "Signed event delivery, retries, dead letters and replay."},
            {"name": "Credentials", "description": "Reusable signed verification credentials."},
            {"name": "Monitoring", "description": "Ongoing screening and alerts."},
            {"name": "Billing and usage", "description": "Metered usage and invoices."},
            {"name": "Businesses (KYB)", "description": "Business records, people, registry evidence and evaluation."},
            {"name": "Review and cases", "description": "Human review, four-eyes decisions, hits and audited media."},
        ],
        "paths": paths,
        "components": COMPONENTS,
        "security": [],
    }


def main():
    spec = build_spec()
    docs_json = ROOT / "docs" / "openapi.json"
    docs_yaml = ROOT / "docs" / "openapi.yaml"
    public_json = ROOT / "public" / "openapi.json"
    public_yaml = ROOT / "public" / "openapi.yaml"
    json_text = json.dumps(spec, indent=2, ensure_ascii=False) + "\n"
    yaml_text = yaml.safe_dump(spec, sort_keys=False, allow_unicode=False, width=120)
    for path, text in ((docs_json, json_text), (public_json, json_text),
                       (docs_yaml, yaml_text), (public_yaml, yaml_text)):
        path.write_text(text, encoding="utf-8")
    operations = sum(len(methods) for methods in spec["paths"].values())
    print(f"Wrote OpenAPI {spec['openapi']}: {len(spec['paths'])} paths, {operations} operations")


if __name__ == "__main__":
    main()
