export function initializeConfigDisclosures(root) {
  const triggers = [...root.querySelectorAll(".config-disclosure")];

  for (const trigger of triggers) {
    const panel = root.getElementById(trigger.getAttribute("aria-controls"));
    if (!panel) continue;

    trigger.setAttribute("aria-expanded", "true");
    panel.hidden = false;
    trigger.addEventListener("click", () => {
      const expanded = trigger.getAttribute("aria-expanded") === "true";
      trigger.setAttribute("aria-expanded", String(!expanded));
      panel.hidden = expanded;
    });
  }
}
