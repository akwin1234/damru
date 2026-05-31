# Contributing to Damru

First off, thank you for considering contributing to Damru! It's people like you that make Damru the apex predator of Android browser automation.

## 🤖 AI-Assisted Development & "Vibe Coding"

Damru is a **vibe-coded** project. This means it was built with a heavy focus on rapid experimentation, deep technical intuition, and a "just make it work" philosophy. 

We would like to acknowledge the following AI tools that served as primary "co-pilots" in the development of this framework:
*   **OpenAI Codex**
*   **Claude Code**
*   **Kimi CLI**

These tools were instrumental in research, C++ binary patching, and orchestrating the complex interactions between Android's OS layers and Playwright.

## 🚀 How Can I Contribute?

### 1. Reporting Bugs
If you find a bug (e.g., an anti-bot successfully detecting Damru), please open an issue. Provide:
*   The target URL.
*   Your device profile and proxy setup.
*   Logs (with `debug=True`).

### 2. Suggesting Enhancements
We are always looking to improve our stealth layers. If you know of a new fingerprinting vector (e.g., a new WebGL extension check), open an issue with your research.

### 3. Code Contributions
We welcome Pull Requests!
*   **Zero JS Philosophy:** Ensure your fixes do not rely on JavaScript injection (`Object.defineProperty`). We solve problems at the OS, Binary, or CDP layer.
*   **Write Tests:** Any new spoofing mechanism must include a corresponding test in the `tests/` folder.
*   **Run the Suite:** Run the full `pytest` suite before submitting your PR to ensure no regressions.

## 🛠️ Development Setup

1. Clone the repo.
2. Setup a virtual environment: `python3 -m venv venv && source venv/bin/activate`
3. Install editable: `pip install -e .`
4. Make your changes on a new branch.

We look forward to reviewing your PR!