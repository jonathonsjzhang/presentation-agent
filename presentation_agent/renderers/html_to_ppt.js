#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const os = require("os");

function requireFirst(candidates) {
  const errors = [];
  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch (err) {
      errors.push(`${candidate}: ${err.message}`);
    }
  }
  throw new Error(errors.join("\n"));
}

function firstExisting(candidates) {
  for (const candidate of candidates) {
    if (candidate && fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return undefined;
}

async function main() {
  const [, , htmlPath, pptxPath] = process.argv;
  if (!htmlPath || !pptxPath) {
    throw new Error("usage: html_to_ppt.js <input.html> <output.pptx>");
  }

  const home = os.homedir();
  const bundledNodeModules = path.join(
    home,
    ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules"
  );
  const { chromium } = requireFirst([
    "playwright",
    path.join(home, ".nvm/versions/node/v20.20.0/lib/node_modules/playwright"),
    path.join(bundledNodeModules, "playwright"),
  ]);
  const pptxgen = requireFirst([
    "pptxgenjs",
    path.join(process.cwd(), "node_modules", "pptxgenjs"),
    path.join(bundledNodeModules, "pptxgenjs"),
  ]);

  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "presentation-agent-html-ppt-"));
  const executablePath = firstExisting([
    process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
    path.join(
      home,
      "Library/Caches/ms-playwright/chromium_headless_shell-1200/chrome-headless-shell-mac-arm64/chrome-headless-shell"
    ),
    path.join(
      home,
      "Library/Caches/ms-playwright/chromium-1200/chrome-mac-arm64/Chromium.app/Contents/MacOS/Chromium"
    ),
  ]);
  let browser;
  try {
    browser = await chromium.launch({ headless: true, executablePath });
    const page = await browser.newPage({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 2 });
    await page.goto(`file://${path.resolve(htmlPath)}`, { waitUntil: "networkidle" });
    const units = page.locator(".unit");
    const count = await units.count();
    if (!count) {
      throw new Error("no .unit elements found in HTML");
    }

    const pptx = new pptxgen();
    pptx.layout = "LAYOUT_WIDE";
    pptx.author = "presentation_agent";
    pptx.subject = "HTML-first PPT export";
    pptx.title = path.basename(pptxPath, ".pptx");
    pptx.company = "presentation_agent";
    pptx.lang = "zh-CN";
    pptx.theme = {
      headFontFace: "Georgia",
      bodyFontFace: "Arial",
      lang: "zh-CN",
    };

    for (let i = 0; i < count; i += 1) {
      const imagePath = path.join(tmpDir, `slide-${String(i + 1).padStart(3, "0")}.png`);
      await units.nth(i).screenshot({ path: imagePath, animations: "disabled" });
      const slide = pptx.addSlide();
      slide.background = { color: "FFFFFF" };
      slide.addImage({ path: imagePath, x: 0, y: 0, w: 13.333333, h: 7.5 });
    }

    fs.mkdirSync(path.dirname(path.resolve(pptxPath)), { recursive: true });
    await pptx.writeFile({ fileName: pptxPath });
  } finally {
    if (browser) {
      await browser.close().catch(() => {});
    }
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
}

main().catch((err) => {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
