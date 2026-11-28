import { build } from 'esbuild';
import { cp, mkdir } from 'node:fs/promises';
await build({ entryPoints: ['src.js'], bundle: true, format: 'iife', target: 'es2020', minify: true, outfile: 'app.js' });
await build({ entryPoints: ['pdf-reader-src.js'], bundle: true, format: 'esm', target: 'es2022', minify: true, outfile: 'pdf-reader.js' });
await cp('node_modules/pdfjs-dist/build/pdf.worker.min.mjs', 'pdf.worker.js');
await mkdir('pdf-assets', { recursive: true });
for (const directory of ['cmaps', 'standard_fonts']) {
  await cp(`node_modules/pdfjs-dist/${directory}`, `pdf-assets/${directory}`, { recursive: true });
}
await mkdir('pdf-assets/wasm', { recursive: true });
for (const name of ['jbig2_nowasm_fallback.js', 'openjpeg_nowasm_fallback.js', 'LICENSE_JBIG2', 'LICENSE_OPENJPEG', 'LICENSE_PDFJS_JBIG2', 'LICENSE_PDFJS_OPENJPEG']) {
  await cp(`node_modules/pdfjs-dist/wasm/${name}`, `pdf-assets/wasm/${name}`);
}
await cp('node_modules/pdfjs-dist/LICENSE', 'pdf-assets/LICENSE');
