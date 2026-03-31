import { test, expect } from "@playwright/test";

test.describe("Login page", () => {
  test("shows login form on /login", async ({ page }) => {
    await page.goto("http://localhost:3001/login");
    await expect(page.getByText("勞基法查詢系統")).toBeVisible();
    await expect(page.getByText("輸入 Email 以收取驗證碼")).toBeVisible();
    await expect(page.getByPlaceholder("your@email.com")).toBeVisible();
    await expect(page.getByRole("button", { name: "寄送驗證碼" })).toBeVisible();
  });

  test("send OTP button disabled when email is empty", async ({ page }) => {
    await page.goto("http://localhost:3001/login");
    const btn = page.getByRole("button", { name: "寄送驗證碼" });
    await expect(btn).toBeDisabled();
  });

  test("send OTP button enabled after typing email", async ({ page }) => {
    await page.goto("http://localhost:3001/login");
    await page.getByPlaceholder("your@email.com").fill("test@example.com");
    await expect(page.getByRole("button", { name: "寄送驗證碼" })).toBeEnabled();
  });

  test("shows OTP input step after clicking send (mock API success)", async ({ page }) => {
    await page.route("**/api/auth/otp/send", (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ detail: "驗證碼已寄出" }) })
    );
    await page.goto("http://localhost:3001/login");
    await page.getByPlaceholder("your@email.com").fill("test@example.com");
    await page.getByRole("button", { name: "寄送驗證碼" }).click();
    await expect(page.getByText("驗證碼已寄至 test@example.com")).toBeVisible();
    // 6 OTP digit inputs
    const inputs = page.locator("input[maxlength='1']");
    await expect(inputs).toHaveCount(6);
  });

  test("shows error when API returns error", async ({ page }) => {
    await page.route("**/api/auth/otp/send", (route) =>
      route.fulfill({ status: 502, body: JSON.stringify({ detail: "無法寄送驗證碼，請稍後再試" }) })
    );
    await page.goto("http://localhost:3001/login");
    await page.getByPlaceholder("your@email.com").fill("test@example.com");
    await page.getByRole("button", { name: "寄送驗證碼" }).click();
    await expect(page.getByText("無法寄送驗證碼，請稍後再試")).toBeVisible();
  });

  test("OTP verify button disabled until all 6 digits filled", async ({ page }) => {
    await page.route("**/api/auth/otp/send", (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ detail: "ok" }) })
    );
    await page.goto("http://localhost:3001/login");
    await page.getByPlaceholder("your@email.com").fill("test@example.com");
    await page.getByRole("button", { name: "寄送驗證碼" }).click();
    await expect(page.getByRole("button", { name: "驗證" })).toBeDisabled();
  });

  test("existing user: OTP verify does not show role selection", async ({ page }) => {
    // Note: after OTP verify, the app calls router.push("/").
    // Next.js middleware runs server-side and cannot be intercepted by page.route(),
    // so the middleware will redirect back to /login (no real session cookie set).
    // We verify that the role selection screen is NOT shown (i.e., not a new user flow).
    await page.route("**/api/auth/otp/send", (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ detail: "ok" }) })
    );
    await page.route("**/api/auth/otp/verify", (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ is_new_user: false }) })
    );
    await page.goto("http://localhost:3001/login");
    await page.getByPlaceholder("your@email.com").fill("test@example.com");
    await page.getByRole("button", { name: "寄送驗證碼" }).click();
    const inputs = page.locator("input[maxlength='1']");
    for (let i = 0; i < 6; i++) {
      await inputs.nth(i).fill(String(i + 1));
    }
    await page.getByRole("button", { name: "驗證" }).click();
    // Role selection should NOT appear (this is an existing user)
    await expect(page.getByText("請選擇你的身份")).not.toBeVisible();
  });

  test("new user: OTP verify shows role selection", async ({ page }) => {
    await page.route("**/api/auth/otp/send", (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ detail: "ok" }) })
    );
    await page.route("**/api/auth/otp/verify", (route) =>
      route.fulfill({
        status: 200,
        body: JSON.stringify({ is_new_user: true, pending_token: "test-token" }),
      })
    );
    await page.goto("http://localhost:3001/login");
    await page.getByPlaceholder("your@email.com").fill("new@example.com");
    await page.getByRole("button", { name: "寄送驗證碼" }).click();
    const inputs = page.locator("input[maxlength='1']");
    for (let i = 0; i < 6; i++) {
      await inputs.nth(i).fill(String(i + 1));
    }
    await page.getByRole("button", { name: "驗證" }).click();
    await expect(page.getByText("請選擇你的身份")).toBeVisible();
    await expect(page.getByText("人資（HR）")).toBeVisible();
    await expect(page.getByText("員工")).toBeVisible();
  });

  test("back button returns to email step", async ({ page }) => {
    await page.route("**/api/auth/otp/send", (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ detail: "ok" }) })
    );
    await page.goto("http://localhost:3001/login");
    await page.getByPlaceholder("your@email.com").fill("test@example.com");
    await page.getByRole("button", { name: "寄送驗證碼" }).click();
    await page.getByText("← 重新輸入 email").click();
    await expect(page.getByPlaceholder("your@email.com")).toBeVisible();
  });
});

test.describe("Middleware auth guard", () => {
  test("redirects to /login when no session cookie", async ({ page }) => {
    // Mock /api/auth/me to return 401 (no session)
    await page.route("**/api/auth/me", (route) =>
      route.fulfill({ status: 401, body: JSON.stringify({ detail: "Not authenticated" }) })
    );
    await page.goto("http://localhost:3001/");
    await expect(page).toHaveURL(/\/login/);
  });
});
