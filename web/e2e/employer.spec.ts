import { expect, test } from "@playwright/test";

/** Minimal TOTP (RFC 6238, HMAC-SHA1, 30s) so the e2e can log in as the seeded
 * staff without external dependencies. The seed uses the fixed secret below. */
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

async function login(page: import("@playwright/test").Page, email: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill("demo-password-123");
  await page.getByLabel("TOTP code").fill(await totpCode(E2E_TOTP_SECRET_B32));
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/queue");
}

test("employer admin sees the wallet balance and k-anonymized cells only", async ({ page }) => {
  await login(page, "employer-admin-e2e@sisi.demo");
  await page.goto("/employer");

  const balance = page.getByTestId("employer-wallet-balance");
  await expect(balance).toBeVisible();
  const amount = Number((await balance.innerText()).replace(/[^\d]/g, ""));
  expect(Number.isNaN(amount)).toBe(false);
  expect(amount).toBeGreaterThanOrEqual(0);

  // 25 linked employees were seeded, so the aggregate cells render — and the
  // small band cells (YELLOW/ORANGE/RED, each below MIN_K) come back suppressed
  // as a dash, never as a small number (spec 3.4).
  const cells = page.getByTestId("employer-dashboard-cells");
  await expect(cells).toBeVisible();
  await expect(cells.getByText("band_GREEN")).toBeVisible();
  expect(await cells.locator("td", { hasText: "—" }).count()).toBeGreaterThan(0);

  // Aggregate-only posture: no employee-level data on the page.
  const body = await page.locator("body").innerText();
  expect(body).not.toContain("indicators");
  expect(body).not.toContain("answers");
});

test("a role without employer permissions gets the role alert", async ({ page }) => {
  await login(page, "nurse-e2e@sisi.demo");
  await page.goto("/employer");
  await expect(page.getByTestId("employer-role-alert")).toBeVisible();
  await expect(page.getByTestId("employer-wallet-balance")).toHaveCount(0);
});
