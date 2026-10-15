import { expect, test, type APIResponse, type Page } from "@playwright/test";

/** Minimal TOTP (RFC 6238, HMAC-SHA1, 30s) so the e2e can log in as a seeded
 * staff member without external dependencies. The seed pins this fixed secret
 * (scripts/seed_corridor_demo.py, scripts/seed_school_demo.py). */
const E2E_TOTP_SECRET_B32 = "JBSWY3DPEHPK3PXP"; // "Hello!" in base32 — demo-only

function base32Decode(input: string): Uint8Array {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = 0;
  let value = 0;
  const out: number[] = [];
  for (const ch of input.toUpperCase().replace(/=+$/, "")) {
    value = (value << 5) | alphabet.indexOf(ch);
    bits += 5;
    if (bits >= 8) {
      out.push((value >>> (bits - 8)) & 0xff);
      bits -= 8;
    }
  }
  return Uint8Array.from(out);
}

async function hmacSha1(key: Uint8Array, message: Uint8Array): Promise<Uint8Array> {
  const cryptoKey = await crypto.subtle.importKey("raw", key, { name: "HMAC", hash: "SHA-1" }, false, [
    "sign",
  ]);
  return new Uint8Array(await crypto.subtle.sign("HMAC", cryptoKey, message));
}

async function totpCode(secretB32: string): Promise<string> {
  const counter = Math.floor(Date.now() / 30_000);
  const message = new Uint8Array(8);
  new DataView(message.buffer).setUint32(4, counter, false);
  const digest = await hmacSha1(base32Decode(secretB32), message);
  const offset = digest[19] & 0x0f;
  const binary =
    ((digest[offset] & 0x7f) << 24) |
    ((digest[offset + 1] & 0xff) << 16) |
    ((digest[offset + 2] & 0xff) << 8) |
    (digest[offset + 3] & 0xff);
  return String(binary % 1_000_000).padStart(6, "0");
}

async function login(page: Page, email: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill("demo-password-123");
  await page.getByLabel("TOTP code").fill(await totpCode(E2E_TOTP_SECRET_B32));
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/queue");
}

const NURSE_EMAIL = "nurse-e2e@sisi.demo";
const GYN_EMAIL = "gyn-e2e@sisi.demo";

/** Synthetic seed patients (scripts/seed_corridor_demo.py: adult-a, adult-b,
 * minor-m). The task brief's +2547000100xx block is kept as a fallback so the
 * spec still finds a patient if a different seed is loaded; a single override
 * can be supplied through SISI_E2E_PATIENT_PHONE. */
// Playwright executes specs in Node; this project ships no @types/node.
declare const process: { env: Record<string, string | undefined> };

const PATIENT_PHONES: string[] = [
  process.env.SISI_E2E_PATIENT_PHONE ?? "",
  "+254700000201",
  "+254700000202",
  "+254700000203",
  "+254700010001",
  "+254700010002",
  "+254700010003",
].filter((phone) => phone !== "");

/** A stable synthetic device id — device binding is per user, and re-using one
 * keeps the test idempotent. */
const PATIENT_DEVICE_ID = "01930000-0000-7000-8000-0000000e2e00";

/** Staff tokens live in sessionStorage only (src/api.ts). */
async function staffTokenFor(page: Page, email: string): Promise<string> {
  await login(page, email);
  const token = await page.evaluate(() => sessionStorage.getItem("sisi_staff_token"));
  expect(token, `${email} should have received a staff token`).toBeTruthy();
  return token as string;
}

function bearer(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

interface Envelope<T> {
  success: boolean;
  data: T | null;
  error: { code: string; message: string } | null;
}

async function envelopeData<T>(resp: APIResponse): Promise<T> {
  const body = (await resp.json()) as Envelope<T>;
  expect(body.success, `expected an ok envelope, got ${JSON.stringify(body.error)}`).toBe(true);
  return body.data as T;
}

/** The staff JWT `sub` is the staff id (app/auth/tokens.py) — that is the
 * gynecologist_id the schedule endpoint needs. */
async function staffIdFromToken(page: Page, token: string): Promise<string> {
  return page.evaluate((raw) => {
    const payload = raw.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return (JSON.parse(atob(payload)) as { sub: string }).sub;
  }, token);
}

/** Dev OTP login (settings.otp_dev_return; dev/demo only). Returns null for a
 * phone that is not a seeded patient — verification of an unknown number is
 * refused unless a birth date is supplied, which would create a new account. */
async function otpLoginExisting(
  page: Page,
  phone: string,
): Promise<{ userId: string; token: string } | null> {
  const requested = await page.request.post("/v1/auth/otp/request", { data: { phone } });
  if (!requested.ok()) return null; // rate limited or rejected — try the next phone
  const { dev_otp: code } = await envelopeData<{ dev_otp?: string }>(requested);
  if (!code) return null;
  const verified = await page.request.post("/v1/auth/otp/verify", {
    data: { phone, code, device_id: PATIENT_DEVICE_ID },
  });
  if (!verified.ok()) return null;
  const session = await envelopeData<{ access_token: string; user_id: string }>(verified);
  return { userId: session.user_id, token: session.access_token };
}

/** Walks the candidate seed phones until one of them owns the referral. */
async function patientOwning(
  page: Page,
  ownerUserId: string,
): Promise<{ phone: string; userId: string; token: string } | null> {
  for (const phone of PATIENT_PHONES) {
    const session = await otpLoginExisting(page, phone);
    if (session && session.userId === ownerUserId) return { phone, ...session };
  }
  return null;
}

/** Value for an <input type="datetime-local">, a day ahead of now. */
function futureLocalIso(hoursAhead = 24): string {
  const when = new Date(Date.now() + hoursAhead * 3_600_000);
  const local = new Date(when.getTime() - when.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

interface QueueRow {
  request_id: string;
  pseudonym: string;
  band: string;
  status: string;
  age_band: string;
  chaperone_requested: boolean;
}

interface FacilityRow {
  id: string;
  name: string;
  county: string;
  stale: boolean;
  warning: string | null;
}

interface ReferralRow {
  id: string;
  user_id: string;
  status: string;
  sections: string[];
}

test("a pending corridor request is reviewed, scheduled, started and completed", async ({ page }) => {
  // Assumes the freshly seeded corridor demo world (scripts/seed_corridor_demo.py),
  // like console.spec.ts does for the school data.
  await login(page, NURSE_EMAIL);
  await page.goto("/corridor");

  // The adult request awaiting nurse review — NOT the minor's, whose session
  // additionally requires a confirmed chaperone (spec 5.4).
  const pending = page
    .getByTestId("corridor-row")
    .filter({ hasText: "pending_nurse_review" })
    .filter({ hasNotText: "chaperone requested" })
    .first();
  await expect(pending, "a seeded adult request should await nurse review").toBeVisible();
  await pending.click();
  await page.waitForURL(/\/corridor\/[0-9a-f-]{36}$/);
  const requestId = page.url().split("/").pop() as string;

  await expect(page.getByTestId("consult-status")).toHaveText("pending_nurse_review");
  await page.getByTestId("approve-btn").click();
  await expect(page.getByTestId("consult-status")).toHaveText("approved");

  // The gynecologist books the room for herself, then runs the consult.
  const gynToken = await staffTokenFor(page, GYN_EMAIL);
  const gynecologistId = await staffIdFromToken(page, gynToken);
  await page.goto(`/corridor/${requestId}`);
  await expect(page.getByTestId("consult-status")).toHaveText("approved");

  await page.getByTestId("gynecologist-id").fill(gynecologistId);
  await page.getByTestId("scheduled-at").fill(futureLocalIso());
  await page.getByTestId("modality").selectOption("video");
  await page.getByTestId("schedule-btn").click();
  await expect(page.getByTestId("session-id")).toBeVisible();
  await expect(page.getByTestId("session-status")).toHaveText("scheduled");

  await page.getByTestId("session-start-btn").click();
  await expect(page.getByTestId("session-status")).toHaveText("in_progress");
  await expect(page.getByTestId("room-link")).toBeVisible();
  await expect(page.getByTestId("room-token")).toBeVisible();

  await page.getByTestId("session-outcome").selectOption("completed");
  await page.getByTestId("session-complete-btn").click();
  await expect(page.getByTestId("session-status")).toHaveText("completed");
});

test("a referral letter is unreadable until the patient approves it", async ({ page }) => {
  const nurseToken = await staffTokenFor(page, NURSE_EMAIL);

  const queue = await envelopeData<QueueRow[]>(
    await page.request.get("/v1/corridor/queue", { headers: bearer(nurseToken) }),
  );
  expect(queue.length, "the seeded corridor queue should not be empty").toBeGreaterThan(0);
  const facilities = await envelopeData<FacilityRow[]>(
    await page.request.get("/v1/corridor/facilities", { headers: bearer(nurseToken) }),
  );
  const facilityId = facilities.length > 0 ? facilities[0].id : null;

  // Drafting a referral is corridor:referrals, which the nurse role does not
  // hold (app/auth/rbac.py) — fall back to the gynecologist, who does.
  const draft = {
    request_id: queue[0].request_id,
    facility_id: facilityId,
  };
  let staffToken = nurseToken;
  let created = await page.request.post("/v1/corridor/referrals", {
    headers: bearer(staffToken),
    data: draft,
  });
  if (!created.ok()) {
    staffToken = await staffTokenFor(page, GYN_EMAIL);
    created = await page.request.post("/v1/corridor/referrals", {
      headers: bearer(staffToken),
      data: draft,
    });
  }
  const referral = await envelopeData<{ id: string; status: string }>(created);
  expect(referral.status).toBe("awaiting_approval");

  // 1. No patient approval recorded -> the letter PDF is refused (409 envelope).
  const beforeApproval = await page.request.get(`/v1/corridor/referrals/${referral.id}/pdf`, {
    headers: bearer(staffToken),
  });
  expect(beforeApproval.status()).toBe(409);
  const refusal = (await beforeApproval.json()) as Envelope<null>;
  expect(refusal.success).toBe(false);
  expect(refusal.error?.code).toBe("conflict");

  // 2. The patient logs in with her own phone (dev OTP) and reads the letter
  //    in full before approving a single section.
  const referrals = await envelopeData<ReferralRow[]>(
    await page.request.get("/v1/corridor/referrals", { headers: bearer(staffToken) }),
  );
  const owner = referrals.find((row) => row.id === referral.id);
  expect(owner, "the drafted referral should be listed").toBeTruthy();
  const patient = await patientOwning(page, owner?.user_id ?? "");
  expect(
    patient,
    `no seeded patient matched referral owner ${owner?.user_id}; tried ${PATIENT_PHONES.join(", ")}`,
  ).not.toBeNull();

  const preview = await page.request.get(`/v1/corridor/referrals/${referral.id}/preview`, {
    headers: bearer(patient?.token ?? ""),
  });
  expect(preview.status(), "the patient must be able to read the letter first").toBe(200);

  const approval = await envelopeData<{ status: string; approved_sections: string[] }>(
    await page.request.post(`/v1/corridor/referrals/${referral.id}/approve`, {
      headers: bearer(patient?.token ?? ""),
      data: { approved_sections: ["triage_summary"] },
    }),
  );
  expect(approval.status).toBe("approved");
  expect(approval.approved_sections).toEqual(["triage_summary"]);

  // 3. Now the PDF renders — from the approved sections only.
  const afterApproval = await page.request.get(`/v1/corridor/referrals/${referral.id}/pdf`, {
    headers: bearer(staffToken),
  });
  expect(afterApproval.status()).toBe(200);
  expect(afterApproval.headers()["content-type"]).toContain("application/pdf");
  expect((await afterApproval.body()).subarray(0, 4).toString()).toBe("%PDF");

  // 4. Revoking takes the letter away again.
  await envelopeData(
    await page.request.post(`/v1/corridor/referrals/${referral.id}/revoke`, {
      headers: bearer(patient?.token ?? ""),
    }),
  );
  const afterRevoke = await page.request.get(`/v1/corridor/referrals/${referral.id}/pdf`, {
    headers: bearer(staffToken),
  });
  expect(afterRevoke.status()).toBe(409);
});

test("stale facility entries are flagged and the fresh one is not", async ({ page }) => {
  await login(page, NURSE_EMAIL);
  await page.goto("/facilities");
  await expect(page.getByTestId("facility-row").first()).toBeVisible();

  // Seeded: Kisumu verified 120 days ago, Mombasa never verified -> both stale.
  await expect
    .poll(() => page.getByTestId("stale-badge").count())
    .toBeGreaterThanOrEqual(2);
  await expect(page.getByTestId("stale-badge").first()).toContainText(
    "not verified in the last 90 days",
  );
  await expect(page.getByTestId("facility-warning").first()).toContainText(
    "not verified in the last 90 days",
  );

  // Seeded: Nairobi verified 30 days ago -> fresh, and no warning on that row.
  await expect
    .poll(() => page.getByTestId("fresh-badge").count())
    .toBeGreaterThanOrEqual(1);
  const freshRow = page
    .getByTestId("facility-row")
    .filter({ has: page.getByTestId("fresh-badge") })
    .first();
  await expect(freshRow.getByTestId("facility-warning")).toHaveCount(0);
});

test("the corridor queue never renders raw symptom values", async ({ page }) => {
  await login(page, NURSE_EMAIL);
  await page.goto("/corridor");
  await expect(page.getByTestId("corridor-row").first()).toBeVisible();

  // Non-negotiable 5: the queue lists pseudonyms, bands and flags only — the
  // encrypted feature snapshot is opened on the case view alone.
  const text = (await page.locator("body").innerText()).toLowerCase();
  for (const forbidden of ["pain", "discharge", "bleeding", "answers", "features"]) {
    expect(text, `the corridor queue must not render "${forbidden}"`).not.toContain(forbidden);
  }
  // Prove the queue rendered real rows, not an empty state.
  expect(text).toMatch(/pending_nurse_review|approved|scheduled|completed/);
});
