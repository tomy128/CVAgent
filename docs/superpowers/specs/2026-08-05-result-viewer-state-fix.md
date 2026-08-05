# Result Viewer State Fix

The viewer currently switches to rendered mode before placing the selected artifact into the source textarea. Rendering reads the empty textarea and overwrites the in-memory result, so every tab appears blank despite non-empty files.

Initialize the textarea and review source first, then select the display mode and render once. This must work for existing Runs without regeneration.

Review controls are contextual: show approve/reject only for `tailored-resume.md` while a Run waits for review. Other artifacts are read-only. A safety-failed Run shows “事实安全未通过” and explains that diagnostic artifacts cannot be approved; it must not claim verification succeeded. Add regression coverage for initialization order, contextual actions, and failure copy, then run the full suite and JavaScript validation.
