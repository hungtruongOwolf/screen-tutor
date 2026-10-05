// Turns plain formula text into SVG text content: powers become raised text and a
// few ASCII spellings become symbols. Always escapes, so a label cannot inject markup.
//
//   "5^2 + 12^2 = 13^2"  ->  5<sup>2</sup> + 12<sup>2</sup> = 13<sup>2</sup>
//   "sqrt(169) = 13"     ->  √(169) = 13

export function escapeXml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

const POWER = /\^(\{[^}]*\}|[+-]?[A-Za-z0-9.]+)/g;

const SYMBOLS: Array<[string, string]> = [
  ["sqrt(", "√("],
  ["<=", "≤"],
  [">=", "≥"],
  ["!=", "≠"],
  ["~=", "≈"],
  ["->", "→"],
  ["*", "×"],
];

function symbols(text: string): string {
  return SYMBOLS.reduce((result, [from, to]) => result.replaceAll(from, to), text);
}

export function formatMath(text: string): string {
  const replaced = symbols(text);
  let out = "";
  let last = 0;
  for (const match of replaced.matchAll(POWER)) {
    const index = match.index ?? 0;
    out += escapeXml(replaced.slice(last, index));
    const raw = match[1] ?? "";
    const exponent = raw.startsWith("{") ? raw.slice(1, -1) : raw;
    out += `<tspan baseline-shift="super" font-size="70%">${escapeXml(exponent)}</tspan>`;
    last = index + match[0].length;
  }
  return out + escapeXml(replaced.slice(last));
}

// The text as it reads without markup (powers kept as ^), for sizing a box around it.
export function plainMath(text: string): string {
  return symbols(text).replace(POWER, (_m, exponent: string) => exponent.replace(/[{}]/g, ""));
}
