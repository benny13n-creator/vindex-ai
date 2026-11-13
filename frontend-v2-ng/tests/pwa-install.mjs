// Targeted browser check for the V2 install entry point. No external API calls.
import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import http from "node:http";

const NG = fileURLToPath(new URL("..", import.meta.url));
const REPO = fileURLToPath(new URL("../..", import.meta.url));
const PORT = 4387;
const BASE = `http://127.0.0.1:${PORT}`;
const proc = spawn(process.execPath, ["serve.mjs", String(PORT)], { cwd: NG, stdio: "ignore" });
let browser;
let failures = 0;
let assertions = 0;
function check(name, ok, details = "") {
  assertions++;
  if (!ok) failures++;
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${details ? ` — ${details}` : ""}`);
}
async function ready() {
  for (let i = 0; i < 100; i++) {
    if (await new Promise(resolve => http.get(BASE, response => { response.resume(); resolve(response.statusCode === 200); }).on("error", () => resolve(false)))) return true;
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  return false;
}
try {
  check("lokalni V2 server se pokrenuo", await ready());
  if (proc.exitCode !== null) throw new Error(`V2 server ended with ${proc.exitCode}`);
  browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.route("**/manifest.json", async route => route.fulfill({
    status: 200,
    contentType: "application/manifest+json",
    body: await readFile(join(REPO, "static", "manifest.json"), "utf8"),
  }));
  const page = await ctx.newPage();
  const consoleErrors = [];
  page.on("pageerror", error => consoleErrors.push(String(error)));
  await page.goto(`${BASE}/?instaliraj=1`);
  const dlg = page.locator("#install-app-dialog");
  check("veza sa sajta može direktno da otvori instalaciono uputstvo", await dlg.evaluate(e => e.open));
  check("desktop ima jasno uputstvo", /Chrome-u ili Edge-u/.test(await page.locator("#install-app-instructions").textContent()));
  await page.locator("#install-app-close").click();

  const eventState = await page.evaluate(() => {
    const e = new Event("beforeinstallprompt", { cancelable: true });
    e.prompt = async () => { window.__installPromptCalled = true; };
    e.userChoice = Promise.resolve({ outcome: "accepted", platform: "web" });
    window.dispatchEvent(e);
    return e.defaultPrevented;
  });
  check("browser native prompt događaj je sačuvan za klik korisnika", eventState);
  await page.locator("#install-app-btn").click();
  check("native install dugme se prikaže unutar otvorenog uputstva", !(await page.locator("#install-app-native").isHidden()));
  await page.locator("#install-app-confirm").click();
  await page.waitForFunction(() => window.__installPromptCalled === true);
  check("native install prompt se poziva tek posle korisničkog klika", await page.evaluate(() => window.__installPromptCalled === true));
  check("prihvaćena instalacija zatvara dijalog", !(await dlg.evaluate(e => e.open)));
  await page.evaluate(() => window.dispatchEvent(new Event("appinstalled")));
  check("već instalirana aplikacija uklanja dugme", await page.locator("#install-app-btn").isHidden());
  check("nema grešaka u browser konzoli", consoleErrors.length === 0, consoleErrors.join(" | "));
  await ctx.close();

  const ios = await browser.newContext({
    viewport: { width: 390, height: 844 },
    userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    isMobile: true,
    hasTouch: true,
  });
  await ios.route("**/manifest.json", async route => route.fulfill({
    status: 200,
    contentType: "application/manifest+json",
    body: await readFile(join(REPO, "static", "manifest.json"), "utf8"),
  }));
  const mobile = await ios.newPage();
  await mobile.goto(BASE);
  await mobile.locator("#install-app-btn").click();
  const iosText = await mobile.locator("#install-app-instructions").textContent();
  check("iPhone dobija Safari / Add to Home Screen korake", /Safari-ju/.test(iosText) && /Add to Home Screen/.test(iosText), iosText);
  check("mobilno dugme ostaje vidljivo i bez native prompt događaja", await mobile.locator("#install-app-btn").isVisible());
  check("iOS nema lažno prikazano native prompt dugme", await mobile.locator("#install-app-native").isHidden());
  await ios.close();

  const android = await browser.newContext({
    viewport: { width: 360, height: 800 },
    userAgent: "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    isMobile: true,
    hasTouch: true,
  });
  await android.route("**/manifest.json", async route => route.fulfill({
    status: 200,
    contentType: "application/manifest+json",
    body: await readFile(join(REPO, "static", "manifest.json"), "utf8"),
  }));
  const androidPage = await android.newPage();
  await androidPage.goto(BASE);
  await androidPage.locator("#install-app-btn").click();
  const androidText = await androidPage.locator("#install-app-instructions").textContent();
  check("Android dobija Chrome meni za instalaciju", /Android uređaju/.test(androidText) && /Add to Home screen/.test(androidText), androidText);
  check("instalaciona kontrola ne izaziva horizontalni preliv na telefonu", await androidPage.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await android.close();

  const website = await readFile(join(REPO, "site", "index.html"), "utf8");
  check("javna početna vodi direktno na instalacioni korak", /href="\/app\?instaliraj=1">Dodaj Vindex na uređaj<\/a>/.test(website));
} finally {
  if (browser) await browser.close();
  proc.kill();
}
console.log(`PWA install browser checks: ${assertions - failures}/${assertions} PASS`);
if (failures) process.exit(1);
