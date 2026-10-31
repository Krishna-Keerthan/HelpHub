import { render} from "@testing-library/react";
import { expect, test} from "vitest";
import AppError from "./error";

test("never shows the error message or stack", () => {
  const error = new Error("secret db detail");
  render(<AppError error={error} reset={() => {}} />);
  expect(document.body).not.toHaveTextContent("secret db detail");
  expect(document.body).not.toHaveTextContent(/at .*\.tsx?:\d+/);
});
