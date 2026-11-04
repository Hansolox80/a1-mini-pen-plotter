"""Management of Machine Profiles and Pen Profiles with persistent JSON storage."""

from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from pathlib import Path
from typing import Any, Optional
import uuid

from app.machine.a1_mini import MachineProfile, create_default_a1_mini_profile


@dataclass
class PenProfile:
    """Complete pen configuration including Z contact/lift heights, offsets, and speeds.

    IMPORTANT SAFETY RULE: Never assume Z=0 corresponds to paper contact.
    Default Z values are conservatively elevated (14.0 mm drawing, 18.0 mm pen-up)
    and marked uncalibrated until verified via the Pen Calibration Wizard.
    """
    id: str = "fineliner_04mm"
    name: str = "Fineliner 0.4mm (Default)"
    tip_diameter_mm: float = 0.4
    color_hex: str = "#22C55E"
    # Z Heights (mm) - Never assume Z=0 is paper contact!
    pen_up_z_mm: float = 18.0
    pen_down_z_mm: float = 14.2
    drawing_z_mm: float = 14.0
    lift_height_mm: float = 4.0
    # Fine calibration offsets specific to this pen (mm)
    x_offset_mm: float = 0.0
    y_offset_mm: float = 0.0
    # Speeds (mm/s)
    draw_speed_mm_s: float = 35.0
    travel_speed_mm_s: float = 120.0
    z_speed_mm_s: float = 15.0  # Pen-Up (lift) speed
    z_down_speed_mm_s: float = 8.0  # Pen-Down (controlled smooth descent/plunge speed)
    # Dwell after lowering pen (ms)
    stabilization_delay_ms: int = 60
    is_calibrated: bool = False
    notes: str = "Calibrate physical Z contact height before plotting on the A1 Mini."

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PenProfile:
        z_up = max(1.0, float(data.get("z_speed_mm_s", 15.0)))
        z_down = max(0.5, float(data.get("z_down_speed_mm_s", min(8.0, z_up))))
        return cls(
            id=str(data.get("id", f"pen_{uuid.uuid4().hex[:8]}")),
            name=str(data.get("name", "Custom Pen")),
            tip_diameter_mm=max(0.05, float(data.get("tip_diameter_mm", 0.4))),
            color_hex=str(data.get("color_hex", "#22C55E")),
            pen_up_z_mm=float(data.get("pen_up_z_mm", 18.0)),
            pen_down_z_mm=float(data.get("pen_down_z_mm", 14.2)),
            drawing_z_mm=float(data.get("drawing_z_mm", 14.0)),
            lift_height_mm=max(0.5, float(data.get("lift_height_mm", 4.0))),
            x_offset_mm=float(data.get("x_offset_mm", 0.0)),
            y_offset_mm=float(data.get("y_offset_mm", 0.0)),
            draw_speed_mm_s=max(1.0, float(data.get("draw_speed_mm_s", 35.0))),
            travel_speed_mm_s=max(5.0, float(data.get("travel_speed_mm_s", 120.0))),
            z_speed_mm_s=z_up,
            z_down_speed_mm_s=z_down,
            stabilization_delay_ms=max(0, int(data.get("stabilization_delay_ms", 60))),
            is_calibrated=bool(data.get("is_calibrated", False)),
            notes=str(data.get("notes", "")),
        )


def create_default_pen_profiles() -> list[PenProfile]:
    """Returns built-in starter pen profiles."""
    return [
        PenProfile(
            id="fineliner_04mm",
            name="Fineliner 0.4mm (Micron / Staedtler)",
            tip_diameter_mm=0.4,
            color_hex="#22C55E",
            pen_up_z_mm=18.0,
            pen_down_z_mm=14.2,
            drawing_z_mm=14.0,
            lift_height_mm=4.0,
            draw_speed_mm_s=35.0,
            travel_speed_mm_s=120.0,
            z_speed_mm_s=12.0,
            stabilization_delay_ms=60,
            is_calibrated=False,
            notes="Delicate felt tip — verify Z contact height carefully to avoid crushing the nib.",
        ),
        PenProfile(
            id="ballpoint_standard",
            name="Ballpoint Pen 0.7mm (Spring Mount)",
            tip_diameter_mm=0.7,
            color_hex="#38BDF8",
            pen_up_z_mm=18.5,
            pen_down_z_mm=14.0,
            drawing_z_mm=13.8,
            lift_height_mm=4.5,
            draw_speed_mm_s=50.0,
            travel_speed_mm_s=150.0,
            z_speed_mm_s=15.0,
            stabilization_delay_ms=40,
            is_calibrated=False,
            notes="Standard ballpoint pen — requires firm contact or spring-loaded mount.",
        ),
        PenProfile(
            id="technical_pen_02mm",
            name="Technical Drafting Pen 0.2mm",
            tip_diameter_mm=0.2,
            color_hex="#F59E0B",
            pen_up_z_mm=17.5,
            pen_down_z_mm=14.1,
            drawing_z_mm=14.0,
            lift_height_mm=3.5,
            draw_speed_mm_s=25.0,
            travel_speed_mm_s=100.0,
            z_speed_mm_s=10.0,
            stabilization_delay_ms=80,
            is_calibrated=False,
            notes="High-precision drafting pen — uses slower drawing speed and longer stabilization.",
        ),
        PenProfile(
            id="marker_bold_10mm",
            name="Bold Marker 1.0mm (Sharpie / Posca)",
            tip_diameter_mm=1.0,
            color_hex="#F43F5E",
            pen_up_z_mm=19.0,
            pen_down_z_mm=14.2,
            drawing_z_mm=14.0,
            lift_height_mm=5.0,
            draw_speed_mm_s=45.0,
            travel_speed_mm_s=140.0,
            z_speed_mm_s=15.0,
            stabilization_delay_ms=50,
            is_calibrated=False,
            notes="Broad tip suitable for hatching and bold contours.",
        ),
    ]


class ProfileManager:
    """Loads, saves, duplicates, renames, and deletes machine and pen profiles."""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        if base_dir is None:
            import sys
            if getattr(sys, "frozen", False):
                # When frozen by PyInstaller: prefer profiles adjacent to the executable, else fallback to _internal
                exe_profiles = Path(sys.executable).resolve().parent / "profiles"
                if exe_profiles.exists():
                    base_dir = exe_profiles
                else:
                    base_dir = Path(__file__).resolve().parent.parent.parent / "profiles"
            else:
                # Resolve project root profiles directory
                base_dir = Path(__file__).resolve().parent.parent.parent / "profiles"
        self.base_dir = Path(base_dir)
        self.machines_dir = self.base_dir / "machines"
        self.pens_dir = self.base_dir / "pens"
        self.machines_dir.mkdir(parents=True, exist_ok=True)
        self.pens_dir.mkdir(parents=True, exist_ok=True)

        self.machines: dict[str, MachineProfile] = {}
        self.pens: dict[str, PenProfile] = {}
        self.reload()

    def reload(self) -> None:
        """Loads all machine and pen profiles from disk, seeding defaults if empty."""
        self.machines.clear()
        self.pens.clear()

        # Load machines
        for f in sorted(self.machines_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                prof = MachineProfile.from_dict(data)
                self.machines[prof.id] = prof
            except Exception:
                continue

        if not self.machines:
            default_machine = create_default_a1_mini_profile()
            self.save_machine(default_machine)

        # Load pens
        for f in sorted(self.pens_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                pen = PenProfile.from_dict(data)
                self.pens[pen.id] = pen
            except Exception:
                continue

        if not self.pens:
            for pen in create_default_pen_profiles():
                self.save_pen(pen)

    def save_machine(self, profile: MachineProfile) -> None:
        self.machines[profile.id] = profile
        path = self.machines_dir / f"{profile.id}.json"
        path.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")

    def delete_machine(self, profile_id: str) -> bool:
        if profile_id not in self.machines or len(self.machines) <= 1:
            return False
        if self.machines[profile_id].is_builtin and profile_id == "bambu_a1_mini":
            return False
        del self.machines[profile_id]
        path = self.machines_dir / f"{profile_id}.json"
        if path.exists():
            path.unlink()
        return True

    def duplicate_machine(self, source_id: str, new_name: Optional[str] = None) -> MachineProfile:
        src = self.machines.get(source_id, create_default_a1_mini_profile())
        data = src.to_dict()
        new_id = f"machine_{uuid.uuid4().hex[:8]}"
        data["id"] = new_id
        data["name"] = new_name or f"{src.name} (Copy)"
        data["is_builtin"] = False
        new_prof = MachineProfile.from_dict(data)
        self.save_machine(new_prof)
        return new_prof

    def rename_machine(self, machine_id: str, new_name: str) -> Optional[MachineProfile]:
        m = self.machines.get(machine_id)
        if m is None:
            return None
        m.name = new_name.strip() or m.name
        self.save_machine(m)
        return m

    def save_pen(self, pen: PenProfile) -> None:
        self.pens[pen.id] = pen
        path = self.pens_dir / f"{pen.id}.json"
        path.write_text(json.dumps(pen.to_dict(), indent=2), encoding="utf-8")

    def create_pen(self, name: str = "New Pen Profile") -> PenProfile:
        new_id = f"pen_{uuid.uuid4().hex[:8]}"
        pen = PenProfile(id=new_id, name=name)
        self.save_pen(pen)
        return pen

    def duplicate_pen(self, source_id: str, new_name: Optional[str] = None) -> PenProfile:
        src = self.pens.get(source_id)
        if src is None:
            src = create_default_pen_profiles()[0]
        data = src.to_dict()
        new_id = f"pen_{uuid.uuid4().hex[:8]}"
        data["id"] = new_id
        data["name"] = new_name or f"{src.name} (Copy)"
        new_pen = PenProfile.from_dict(data)
        self.save_pen(new_pen)
        return new_pen

    def rename_pen(self, pen_id: str, new_name: str) -> Optional[PenProfile]:
        pen = self.pens.get(pen_id)
        if pen is None:
            return None
        pen.name = new_name.strip() or pen.name
        self.save_pen(pen)
        return pen

    def delete_pen(self, pen_id: str) -> bool:
        if pen_id not in self.pens or len(self.pens) <= 1:
            return False
        del self.pens[pen_id]
        path = self.pens_dir / f"{pen_id}.json"
        if path.exists():
            path.unlink()
        return True

    def get_default_machine(self) -> MachineProfile:
        if "bambu_a1_mini" in self.machines:
            return self.machines["bambu_a1_mini"]
        return next(iter(self.machines.values()))

    def get_default_pen(self) -> PenProfile:
        if "fineliner_04mm" in self.pens:
            return self.pens["fineliner_04mm"]
        return next(iter(self.pens.values()))
