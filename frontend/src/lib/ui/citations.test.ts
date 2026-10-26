import { expect, test } from "vitest";
import { parseCitations } from "./citations";

// Same fixtures as backend/tests/chat/test_prompt_delimiters.py (test_parse_citations and the lenticular cases).
const FIXTURES: [string, number, number[]][] = [
  ["see [1]", 3, [1]],
  ["see [1][2]", 3, [1, 2]],
  ["see [1, 2]", 3, [1, 2]],
  ["see [0]", 3, []],
  ["see [99]", 3, []],
  ["see [-1]", 3, []],
  ["see [a]", 3, []],
  ["[2] and [2] and [1]", 3, [1, 2]],
  ["[3][1][2]", 3, [1, 2, 3]],
  ["[1, 99]", 3, [1]],
  ["no citations", 3, []],
  ["[1]", 0, []],
  ["see ［1］", 3, [1]],
  ["see ［1, 2］ and 【3】", 3, [1, 2, 3]],
  ["see ［1]", 3, [1]],
  ["see ［１］", 3, []], // fullwidth digit is not a source number
  ["see ［99］", 3, []],
  ["see 【2】", 3, [2]],
  ["see 【1, 3】", 3, [1, 3]],
  ["see 【 2 】", 3, [2]],
  ["see 【2]", 3, [2]], // mixed lenticular open, ASCII close
  ["see 【99】", 3, []],
  ["see 【a】", 3, []],
];

test.each(FIXTURES)("parseCitations(%j, %i) = %j, as the backend does", (answer, n, expected) => {
  expect(parseCitations(answer, n)).toEqual(expected);
});
