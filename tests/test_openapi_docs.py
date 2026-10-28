"""Documentation contract tests.

The OpenAPI document is a product surface: AI agents, customer
backends and client generators import it. These tests pin the
implemented route inventory and the claims made by the developer
documentation so an endpoint or integration boundary cannot drift
silently.
"""
import json
import os
import unittest
import urllib.error
import urllib.request

import yaml

from tests.helpers import Server

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_json(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return json.load(f)


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


EXPECTED_OPERATIONS = {
    ("get", "/docs"), ("get", "/openapi.json"), ("get", "/openapi.yaml"),
    ("get", "/healthz"),
    ("post", "/v1/tenants"),
    ("delete", "/v1/platform/tenants/{tenantId}"),
    ("get", "/v1/platform/metrics"),
    ("post", "/v1/platform/prices"), ("post", "/v1/platform/quotas"),
    ("post", "/v1/platform/invoices"),
    ("post", "/v1/applicants"),
    ("get", "/v1/applicants/{applicantId}"),
    ("delete", "/v1/applicants/{applicantId}"),
    ("post", "/v1/sessions"), ("get", "/v1/sessions"),
    ("get", "/v1/sessions/{sessionId}"),
    ("get", "/v1/sessions/{sessionId}/checks"),
    ("post", "/v1/sessions/{sessionId}/cancel"),
    ("get", "/v1/sessions/{sessionId}/credential"),
    ("get", "/v1/config"), ("put", "/v1/config"),
    ("get", "/v1/keys"), ("post", "/v1/keys/{keyId}/revoke"),
    ("post", "/v1/users"), ("get", "/v1/users"),
    ("post", "/v1/users/{userId}/revoke"),
    ("post", "/v1/users/{userId}/mfa/enroll"),
    ("post", "/v1/users/{userId}/mfa/confirm"),
    ("post", "/v1/users/{userId}/mfa/reset"),
    ("post", "/v1/webhooks"), ("get", "/v1/webhooks"),
    ("delete", "/v1/webhooks/{webhookId}"),
    ("get", "/v1/webhooks/deliveries"),
    ("post", "/v1/webhooks/deliveries/{deliveryId}/replay"),
    ("post", "/v1/credentials/verify"), ("post", "/v1/credentials/revoke"),
    ("post", "/v1/monitoring/rescreen"), ("get", "/v1/monitoring/alerts"),
    ("get", "/v1/usage"), ("get", "/v1/invoices"),
    ("post", "/v1/businesses"), ("get", "/v1/businesses"),
    ("get", "/v1/businesses/{businessId}"),
    ("post", "/v1/businesses/{businessId}/people"),
    ("post", "/v1/businesses/{businessId}/document"),
    ("post", "/v1/businesses/{businessId}/registry-check"),
    ("post", "/v1/businesses/{businessId}/registry"),
    ("post", "/v1/businesses/{businessId}/evaluate"),
    ("get", "/v1/cases"), ("get", "/v1/cases/{caseId}"),
    ("post", "/v1/cases/{caseId}/decide"),
    ("post", "/v1/cases/{caseId}/confirm"),
    ("post", "/v1/cases/{caseId}/hits/{hitId}/dispose"),
    ("get", "/v1/documents/{documentId}/image"),
    ("get", "/v1/biometrics/{biometricId}/image"),
    ("get", "/v1/flow/session"), ("get", "/v1/flow/credential"),
    ("post", "/v1/flow/consent"), ("post", "/v1/flow/document"),
    ("post", "/v1/flow/document/back"), ("post", "/v1/flow/presence"),
    ("post", "/v1/flow/selfie"), ("post", "/v1/flow/liveness/challenge"),
    ("post", "/v1/flow/liveness"), ("post", "/v1/flow/poa"),
    ("post", "/v1/flow/document/process"), ("post", "/v1/flow/document/claim"),
    ("post", "/v1/flow/submit"), ("post", "/v1/flow/credential/revoke"),
}


def raw_get(base, path):
    req = urllib.request.Request(base + path, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.headers.get_content_type(), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get_content_type(), e.read()


class OpenApiDocsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_json("docs/openapi.json")

    def test_generated_copies_match(self):
        self.assertEqual(self.spec, load_json("public/openapi.json"))
        docs_yaml = yaml.safe_load(read("docs/openapi.yaml"))
        public_yaml = yaml.safe_load(read("public/openapi.yaml"))
        self.assertEqual(docs_yaml, public_yaml)
        self.assertEqual(self.spec["openapi"], docs_yaml["openapi"])
        self.assertEqual(set(self.spec["paths"]), set(docs_yaml["paths"]))

    def test_operation_inventory_is_exact(self):
        actual = {
            (method, path)
            for path, methods in self.spec["paths"].items()
            for method in methods
        }
        self.assertEqual(actual, EXPECTED_OPERATIONS)
        self.assertEqual(len(actual), 69)
        self.assertEqual(len(self.spec["paths"]), 63)

    def test_every_operation_is_agent_usable(self):
        operation_ids = []
        for path, methods in self.spec["paths"].items():
            for method, operation in methods.items():
                with self.subTest(method=method, path=path):
                    self.assertTrue(operation.get("operationId"))
                    self.assertTrue(operation.get("summary"))
                    self.assertTrue(operation.get("description"))
                    self.assertTrue(operation.get("tags"))
                    self.assertIn("security", operation)
                    self.assertTrue(operation.get("responses"))
                    for status, response in operation["responses"].items():
                        self.assertTrue(status.isdigit(), status)
                        self.assertTrue(response.get("description"))
                    operation_ids.append(operation["operationId"])
        self.assertEqual(len(operation_ids), len(set(operation_ids)))

    def test_refs_resolve_and_path_params_match(self):
        missing = []

        def resolve(ref):
            current = self.spec
            for part in ref[2:].split("/"):
                part = part.replace("~1", "/").replace("~0", "~")
                if not isinstance(current, dict) or part not in current:
                    return False
                current = current[part]
            return True

        def walk(value):
            if isinstance(value, dict):
                ref = value.get("$ref")
                if ref and ref.startswith("#/") and not resolve(ref):
                    missing.append(ref)
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(self.spec)
        self.assertEqual(missing, [])
        for path, methods in self.spec["paths"].items():
            needed = {
                seg[1:-1] for seg in path.split("/")
                if seg.startswith("{") and seg.endswith("}")
            }
            for operation in methods.values():
                declared = {
                    p["name"] for p in operation.get("parameters", [])
                    if p.get("in") == "path"
                }
                self.assertEqual(declared, needed, path)

    def test_security_models_are_explicit(self):
        schemes = self.spec["components"]["securitySchemes"]
        self.assertEqual(set(schemes), {
            "tenantApiKey", "platformAdmin", "flowTokenBearer", "flowTokenHeader",
        })
        create_session = self.spec["paths"]["/v1/sessions"]["post"]
        self.assertEqual(create_session["security"], [{"tenantApiKey": []}])
        create_tenant = self.spec["paths"]["/v1/tenants"]["post"]
        self.assertEqual(create_tenant["security"], [{"platformAdmin": []}])
        flow_submit = self.spec["paths"]["/v1/flow/submit"]["post"]
        self.assertIn({"flowTokenBearer": []}, flow_submit["security"])
        self.assertIn({"flowTokenHeader": []}, flow_submit["security"])

    def test_no_retired_or_invented_contracts_in_spec(self):
        text = json.dumps(self.spec)
        for forbidden in (
            "session.created",
            "session.expired",
            "session.needs_more_information",
            "/v1/sessions/{sessionId}/documents",
            "/v1/sessions/{sessionId}/selfie",
            "director|ubo|officer",
        ):
            self.assertNotIn(forbidden, text)
        events = self.spec["components"]["schemas"]["WebhookEvent"]["properties"]["event"]["enum"]
        self.assertEqual(events, [
            "session.completed", "case.opened", "case.decided",
            "applicant.deleted", "screening.hit_new",
        ])

    def test_developer_guide_covers_each_product_surface(self):
        guide = read("docs/DEVELOPER.md")
        required = [
            "## 6. Website integration",
            "## 7. Mobile-app integration",
            "## 8. AI-agent integration",
            "SFSafariViewController",
            "Chrome Custom Tab",
            "WKWebView",
            "no public native-capture SDK",
            "return_url",
            "iframe widget",
            "verifyWebhookSignature",
            "dead_letter",
            "Idempotency-Key",
            "not currently honoured",
            "GET /v1/config?level=N",
            "`director` or `ubo`",
            "quota_exceeded",
            "vpn_proxy_detected",
        ]
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, guide)

    def test_sdk_readme_method_map_matches_client(self):
        sdk = read("sdk/kyc.mjs")
        readme = read("sdk/README.md")
        for method in (
            "createApplicant", "createSession", "getSessionChecks",
            "cancelSession", "getSessionCredential", "listKeys",
            "createUser", "decideCase", "disposeCaseHit",
            "uploadBusinessDocument", "decideBusinessRegistry",
            "replayDelivery", "verifyCredential", "rescreen",
            "getUsage", "updateConfig", "absoluteFlowUrl",
        ):
            with self.subTest(method=method):
                self.assertIn(method, sdk)
                self.assertIn(f"`{method}`", readme)
        self.assertIn("{ level, config: patch }", sdk)

    def test_public_routes_and_content_types(self):
        with Server() as srv:
            status, ctype, body = raw_get(srv.base, "/docs")
            self.assertEqual(status, 200)
            self.assertEqual(ctype, "text/html")
            self.assertIn(b"Nova KYC Developers", body)
            self.assertIn(b"/openapi.json", body)

            status, ctype, body = raw_get(srv.base, "/developers")
            self.assertEqual(status, 200)
            self.assertEqual(ctype, "text/html")
            self.assertIn(b"API explorer", body)

            status, ctype, body = raw_get(srv.base, "/openapi.json")
            self.assertEqual(status, 200)
            self.assertEqual(ctype, "application/json")
            self.assertEqual(json.loads(body), self.spec)

            status, ctype, body = raw_get(srv.base, "/openapi.yaml")
            self.assertEqual(status, 200)
            self.assertEqual(ctype, "application/yaml")
            self.assertEqual(yaml.safe_load(body)["openapi"], "3.1.0")


if __name__ == "__main__":
    unittest.main()
