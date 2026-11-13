// Builds the interface: app.ts and preview-window.ts into scriptorum/ui/dist
// (the same esbuild settings as before).
//
// Cytoscape.js 3.34.0 (the relationship chart, F3.9) has a parser for
// stylesheets written as text. Scriptorum never uses it (it passes its styles
// as objects), but three of its regular expressions can backtrack
// exponentially (CodeQL js/redos, alerts 2 to 4, found 13 November 2026).
// They write "any character" as (\s|.) or (?:.|\s), where a space matches both
// halves; [\s\S] means exactly the same with no ambiguity. The build replaces
// them while bundling, and stops if a newer Cytoscape no longer has them, so
// the fix is never lost silently.
import { build } from "esbuild";
import { readFile } from "node:fs/promises";

const CYTOSCAPE_FIXES = [
  ["/[/][*](\\s|.)+?[*][/]/g", "/[/][*][\\s\\S]+?[*][/]/g"],
  ["/^\\s*((?:.|\\s)+?)\\s*\\{((?:.|\\s)+?)\\}/", "/^\\s*([\\s\\S]+?)\\s*\\{([\\s\\S]+?)\\}/"],
];

const safeRegexes = {
  name: "cytoscape-safe-regexes",
  setup(b) {
    b.onLoad({ filter: /node_modules[\\/]cytoscape[\\/]dist[\\/].*\.m?js$/ }, async (args) => {
      let text = await readFile(args.path, "utf8");
      for (const [unsafe, safe] of CYTOSCAPE_FIXES) {
        if (!text.includes(unsafe)) {
          throw new Error(`Cytoscape no longer contains ${unsafe}: check the fix in ui-src/build.mjs`);
        }
        text = text.split(unsafe).join(safe);
      }
      return { contents: text, loader: "js" };
    });
  },
};

await build({
  entryPoints: ["app.ts", "preview-window.ts"],
  bundle: true,
  format: "iife",
  target: "chrome110",
  loader: { ".svg": "text" },
  outdir: "../scriptorum/ui/dist",
  plugins: [safeRegexes],
  logLevel: "info",
});
