#!/usr/bin/env node
// Build-time marketing image optimizer.
//
// The photography in public/marketing ships as large progressive JPEGs (~2.2MB
// for 8 files). This script derives AVIF, WebP and re-encoded JPEG renditions of
// each source at two widths — a compact 800px tier and a full tier capped at
// 1600px — and writes a manifest the SPA imports for intrinsic dimensions (so
// <img width/height> can reserve space and avoid CLS) and for multi-candidate
// `NNNw` <picture> srcsets. The original JPEGs stay where they are and remain
// the <img src> fallback, so nothing breaks if this script has not run.
//
// Re-encodes only when a source is newer than its outputs, so repeat runs are
// cheap and safe. Run automatically as part of `npm run build`; also standalone:
//
//   npm run images
//   node scripts/optimize-images.mjs

import { mkdirSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { dirname, extname, join, resolve, basename } from "node:path";
import { fileURLToPath } from "node:url";

import sharp from "sharp";

const __dirname = dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = resolve(__dirname, "..");
const SOURCE_DIR = join(WEB_ROOT, "public", "marketing");
const OUTPUT_DIR = join(SOURCE_DIR, "optimized");
const MANIFEST_PATH = join(WEB_ROOT, "src", "lib", "marketingImages.generated.js");

// Layout slots top out around half of the max-w-7xl hero split, so 1600px
// covers the largest display box at 2x without shipping the 1920px source.
const FULL_MAX_WIDTH = 1600;
// The compact tier is what full-bleed phone slots resolve to at 2x and half
// column slots at 1x; without it every viewport downloads the full rendition.
const COMPACT_WIDTH = 800;

/** Every format is emitted at every width so <picture> srcsets can mix `NNNw`. */
const FORMATS = [
  { key: "avif", ext: "avif", encode: (img) => img.avif({ quality: 55, effort: 4 }) },
  { key: "webp", ext: "webp", encode: (img) => img.webp({ quality: 78, effort: 4 }) },
  {
    key: "jpg",
    ext: "jpg",
    encode: (img) => img.jpeg({ quality: 78, mozjpeg: true, progressive: true }),
  },
];

function formatBytes(n) {
  return n < 1024 ? `${n} B` : n < 1024 * 1024 ? `${(n / 1024).toFixed(1)} kB` : `${(n / 1024 / 1024).toFixed(2)} MB`;
}

/** public/ paths are served from the site root, not relative to the module. */
function publicUrl(file) {
  return `/marketing/optimized/${file}`;
}

/**
 * Widths to emit for a source of `sourceWidth` px, ascending and deduped.
 * The full tier keeps its historical un-suffixed filename; smaller tiers get a
 * `-NNN` suffix (e.g. hero-fleet-800.avif next to hero-fleet.avif).
 */
function tierWidths(sourceWidth) {
  const full = Math.min(FULL_MAX_WIDTH, sourceWidth);
  const compact = Math.min(COMPACT_WIDTH, sourceWidth);
  return [...new Set([compact, full])].sort((a, b) => a - b);
}

function variantFile(stem, ext, outWidth, fullWidth) {
  return outWidth === fullWidth ? `${stem}.${ext}` : `${stem}-${outWidth}.${ext}`;
}

function listSources() {
  return readdirSync(SOURCE_DIR, { withFileTypes: true })
    .filter((e) => e.isFile() && extname(e.name).toLowerCase() === ".jpg")
    .map((e) => e.name)
    .sort();
}

async function main() {
  mkdirSync(OUTPUT_DIR, { recursive: true });

  const names = listSources();
  if (names.length === 0) {
    console.error(`No source JPEGs found in ${SOURCE_DIR}`);
    process.exit(1);
  }

  const manifest = {};
  let written = 0;
  let skipped = 0;

  for (const name of names) {
    const stem = basename(name, extname(name));
    const sourcePath = join(SOURCE_DIR, name);
    const sourceStat = statSync(sourcePath);
    const meta = await sharp(sourcePath).metadata();
    // EXIF orientations 5-8 store the pixels rotated 90°, so the intrinsic
    // box the browser will see is transposed relative to the raw file.
    const transpose = meta.orientation >= 5 && meta.orientation <= 8;
    const width = transpose ? meta.height : meta.width;
    const height = transpose ? meta.width : meta.height;

    const fullWidth = Math.min(FULL_MAX_WIDTH, width);
    const tiers = tierWidths(width);

    const sources = {};
    for (const format of FORMATS) {
      const variants = [];
      for (const outWidth of tiers) {
        const outName = variantFile(stem, format.ext, outWidth, fullWidth);
        const outPath = join(OUTPUT_DIR, outName);

        if (statSync(outPath, { throwIfNoEntry: false })?.mtimeMs >= sourceStat.mtimeMs) {
          console.log(`  skip ${outName} (up to date)`);
          skipped += 1;
        } else {
          const pipeline = sharp(sourcePath)
            .rotate()
            .resize({ width: outWidth, withoutEnlargement: true });
          await format.encode(pipeline).toFile(outPath);
          console.log(`  wrote ${outName} (${formatBytes(statSync(outPath).size)})`);
          written += 1;
        }

        // Intrinsic size of the file the browser will actually fetch, which is
        // what `NNNw` descriptors and per-variant sizing need. Read from disk
        // so skipped outputs report the same numbers as freshly written ones.
        const outMeta = await sharp(outPath).metadata();
        variants.push({
          url: publicUrl(outName),
          width: outMeta.width,
          height: outMeta.height,
        });
      }
      sources[format.key] = variants;
    }

    manifest[stem] = {
      src: `/marketing/${name}`,
      width,
      height,
      sources,
    };
  }

  const banner = [
    "// AUTO-GENERATED by scripts/optimize-images.mjs — do not edit by hand.",
    "// Run `npm run images` (or `npm run build`) to regenerate.",
    "// Keys are public/marketing filename stems; values carry the source's",
    "// intrinsic dimensions (for <img width/height>) plus, under `sources`,",
    "// ascending {url, width, height} variants per format (avif/webp/jpg) for",
    "// MarketingImage to turn into `NNNw` srcsets.",
  ].join("\n");
  writeFileSync(MANIFEST_PATH, `${banner}\nexport const marketingImageManifest = ${JSON.stringify(manifest, null, 2)};\n`);
  console.log(`  wrote ${MANIFEST_PATH.slice(WEB_ROOT.length + 1)} (${names.length} images)`);
  console.log(`optimize-images: ${written} file(s) written, ${skipped} up to date`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
