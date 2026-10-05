// A caption written for the eye, as it should be read aloud: formulas spoken as words, symbols and
// markup dropped. Pure.

const NUMBER_WORDS: Record<string, string> = { "2": "squared", "3": "cubed" };

export function speakable(caption: string): string {
  let text = caption.replace(/²/g, " squared").replace(/³/g, " cubed");
  // Powers: 5^2 -> "5 squared", x^{10} -> "x to the power 10".
  text = text.replace(/\^\{([^}]*)\}|\^([+-]?[A-Za-z0-9.]+)/g, (_m, braced: string | undefined, plain: string | undefined) => {
    const power = braced ?? plain ?? "";
    return NUMBER_WORDS[power] ? ` ${NUMBER_WORDS[power]}` : ` to the power ${power}`;
  });
  text = text
    .replace(/sqrt\(/g, "the square root of (")
    .replace(/->|=>/g, " then ")
    .replace(/<=/g, " is at most ")
    .replace(/>=/g, " is at least ")
    .replace(/!=/g, " is not equal to ")
    .replace(/~=/g, " is about ")
    .replace(/(\d)\s*\*\s*(\d|\w)/g, "$1 times $2")
    .replace(/\s=\s/g, " equals ")
    .replace(/=/g, " equals ")
    .replace(/\s\+\s/g, " plus ")
    .replace(/(\d)\s*\+\s*(\d)/g, "$1 plus $2")
    .replace(/\s-\s/g, " minus ")
    .replace(/&/g, " and ")
    .replace(/[`*_#>|~]/g, "")
    .replace(/[“”"]/g, "")
    .replace(/\(\s*/g, "(")
    .replace(/\s+/g, " ")
    .trim();
  return text;
}

// Text in pieces of about a sentence, so the first can be played while the next is being made.
export function splitSentences(text: string): string[] {
  const parts = text.match(/[^.!?;:]+[.!?;:]*\s*/g)?.map((p) => p.trim()).filter(Boolean) ?? [];
  // A very short piece (a number, "so,") is joined to the next one.
  const joined: string[] = [];
  for (const part of parts) {
    const last = joined[joined.length - 1];
    if (last !== undefined && last.length < 14) joined[joined.length - 1] = `${last} ${part}`;
    else joined.push(part);
  }
  return joined.length > 0 ? joined : text.trim() ? [text.trim()] : [];
}

