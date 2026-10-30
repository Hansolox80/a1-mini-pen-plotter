## Description
Provide a summary of the changes introduced by this Pull Request and the issue or improvement it addresses.

## Type of Change
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Performance improvement / Refactoring

## Physical & Firmware Safety Checklist
- [ ] Confirmed that no active heating commands (`M104 > 0`, `M109`, `M140 > 0`, `M190`) are introduced.
- [ ] Confirmed that no filament extrusion movements (`E` axis) are emitted in plotting mode.
- [ ] Confirmed that coordinates remain within the Bambu Lab A1 Mini build volume ($180 \times 180\text{ mm}$).
- [ ] Confirmed that controlled pen transitions (`PEN_DOWN` / `PEN_UP`) are strictly maintained.

## Testing & Quality Checklist
- [ ] All automated tests pass without errors (`pytest -v`).
- [ ] Added new test cases covering new features or bug fixes in `tests/test_engine.py` or `tests/test_ui.py`.
- [ ] Verified that the application launches cleanly without UI freezes or unhandled exceptions.
- [ ] Code adheres to PEP 8 standards with appropriate type hints and docstrings.
- [ ] Verified build succeeds with `build_windows.bat` (if applicable).

## Related Issues
Closes #(issue number)
