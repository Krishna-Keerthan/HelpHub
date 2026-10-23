/**
 * Display only: show fullwidth ［n］ and lenticular 【n】 citation markers as ASCII [n].
 * The stored answer, the chips and `done.cited` are untouched.
 */
export function displayCitations(text: string): string {
  return text.replace(/[［【]\s*([0-9０-９]+)\s*[］】]/g, (_m, digits: string) => {
    const ascii = digits.replace(/[０-９]/g, (d) => String(d.charCodeAt(0) - 0xff10));
    return `[${ascii}]`;
  });
}
