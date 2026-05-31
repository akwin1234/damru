## Description
<!-- Please include a summary of the change and which issue is fixed. -->
<!-- Please also include relevant motivation and context. -->

Fixes # (issue)

## Type of change
<!-- Please delete options that are not relevant. -->
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update

## Stealth Philosophy Check
<!-- Damru operates on a strict "Zero JS" philosophy. Please verify the following: -->
- [ ] My change relies on native OS, Binary, or CDP spoofing.
- [ ] I have **NOT** injected JavaScript (`Object.defineProperty`, etc.) to achieve this bypass.

## Checklist:
- [ ] I have performed a self-review of my own code
- [ ] I have commented my code, particularly in hard-to-understand areas (C++ hooks, ADB shell commands)
- [ ] I have made corresponding changes to the documentation
- [ ] I have run the benchmark suite (`python -m damru.benchmark`) and verified no regressions occurred
