#!/usr/bin/env node
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const { pathToFileURL } = require("url");

function requireFirst(candidates) {
  const errors = [];
  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch (error) {
      errors.push(`${candidate}: ${error.message}`);
    }
  }
  throw new Error(errors.join("\n"));
}

function firstExisting(candidates) {
  return candidates.find((candidate) => candidate && fs.existsSync(candidate));
}

async function main() {
  const [, , htmlPath, outputDir] = process.argv;
  if (!htmlPath || !outputDir) {
    throw new Error("usage: html_screenshot.js <input.html> <output-dir>");
  }

  fs.mkdirSync(outputDir, { recursive: true });
  const home = os.homedir();
  const bundledNodeModules = path.join(
    home,
    ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules"
  );
  const { chromium } = requireFirst([
    "playwright",
    path.join(bundledNodeModules, "playwright"),
  ]);
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
    const page = await browser.newPage({
      viewport: { width: 1440, height: 900 },
      deviceScaleFactor: 1.5,
    });
    await page.goto(pathToFileURL(path.resolve(htmlPath)).href, { waitUntil: "load" });
    await page.waitForTimeout(300);

    const images = [];
    const units = page.locator(".unit");
    const unitCount = await units.count();
    if (unitCount > 0) {
      for (let index = 0; index < unitCount; index += 1) {
        const target = path.resolve(
          outputDir,
          `page-${String(index + 1).padStart(3, "0")}.png`
        );
        await units.nth(index).screenshot({ path: target, animations: "disabled" });
        images.push(target);
      }
    } else {
      const height = await page.evaluate(() =>
        Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)
      );
      const viewportHeight = 900;
      let index = 1;
      for (let y = 0; y < height; y += viewportHeight) {
        const target = path.resolve(
          outputDir,
          `page-${String(index).padStart(3, "0")}.png`
        );
        await page.screenshot({
          path: target,
          animations: "disabled",
          clip: {
            x: 0,
            y,
            width: 1440,
            height: Math.min(viewportHeight, height - y),
          },
        });
        images.push(target);
        index += 1;
      }
    }
    process.stdout.write(JSON.stringify({ images, unit_count: images.length }));
  } finally {
    if (browser) {
      await browser.close().catch(() => {});
    }
  }
}

main().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
