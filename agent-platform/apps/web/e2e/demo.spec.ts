import { expect, type Page, test } from "@playwright/test";

const EMAIL = process.env.E2E_EMAIL ?? "admin@example.com";
const PASSWORD = process.env.E2E_PASSWORD ?? "admin-password";

async function login(page: Page) {
  await page.goto("/login");
  await page.fill("#email", EMAIL);
  await page.fill("#password", PASSWORD);
  await page.click("button[type=submit]");
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
}

test("demo: run the Job Application Assistant, approve the proposal, finish", async ({ page }) => {
  await login(page);

  await page.goto("/pipelines");
  await page.getByRole("link", { name: /Job Application Assistant/ }).first().click();
  await expect(page.getByText("Job Application Assistant").first()).toBeVisible();

  await page.getByRole("button", { name: "Run", exact: true }).click();
  await page.getByRole("button", { name: "Start execution" }).click();
  await page.waitForURL(/\/executions\/[0-9a-f-]+$/);
  const executionUrl = page.url();

  // The demo pauses before every side-effecting tool call. Approve each one as it comes up.
  for (let round = 0; round < 5; round++) {
    const review = page.getByRole("link", { name: /Review now/ });
    const completed = page.getByText("Completed", { exact: true }).first();
    await expect(review.or(completed)).toBeVisible({ timeout: 60_000 });
    if (await completed.isVisible()) break;

    await review.click();
    await page.waitForURL(/\/approvals\/[0-9a-f-]+/);
    await page.getByRole("button", { name: /^Approve/ }).click();
    await expect(page.getByText(/Approved/).first()).toBeVisible();
    await page.goto(executionUrl);
  }

  await expect(page.getByText("Completed", { exact: true }).first()).toBeVisible({ timeout: 60_000 });
});

test("prompt studio previews a template with workspace variables", async ({ page }) => {
  await login(page);
  await page.goto("/prompts");
  await page.getByRole("button", { name: /Job filter/ }).click();
  await expect(page.getByText("Sam Rivera")).toBeVisible();
  await expect(page.getByText("workspace variable").first()).toBeVisible();
});
