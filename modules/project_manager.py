import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import config

class ProjectManager:
    def __init__(self, project_name: str):
        # Очистка имени проекта для создания валидной папки
        self.raw_name = project_name
        self.slug = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in project_name.strip()).lower()
        if not self.slug:
            self.slug = "project_default"
        
        self.project_dir = config.PROJECTS_DIR / self.slug
        self.audio_dir = self.project_dir / "audio"
        self.visuals_dir = self.project_dir / "visuals"
        
        self._ensure_dirs()

    def _ensure_dirs(self):
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.visuals_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def list_projects(cls) -> List[str]:
        if not config.PROJECTS_DIR.exists():
            return []
        return [p.name for p in config.PROJECTS_DIR.iterdir() if p.is_dir()]

    def save_raw_material(self, text: str) -> Path:
        path = self.project_dir / "raw_material.txt"
        path.write_text(text, encoding="utf-8")
        return path

    def load_raw_material(self) -> str:
        path = self.project_dir / "raw_material.txt"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def save_script(self, script_md: str, script_json: Optional[Dict[str, Any]] = None) -> Path:
        md_path = self.project_dir / "script.md"
        md_path.write_text(script_md, encoding="utf-8")
        if script_json:
            json_path = self.project_dir / "script.json"
            json_path.write_text(json.dumps(script_json, ensure_ascii=False, indent=2), encoding="utf-8")
        return md_path

    def load_script(self) -> str:
        path = self.project_dir / "script.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def save_voiceover_clean(self, text: str) -> Path:
        path = self.project_dir / "voiceover_clean.txt"
        path.write_text(text, encoding="utf-8")
        return path

    def load_voiceover_clean(self) -> str:
        path = self.project_dir / "voiceover_clean.txt"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def save_prompts(self, prompts_md: str, prompts_json: Optional[List[Dict[str, Any]]] = None) -> Path:
        md_path = self.project_dir / "prompts.md"
        md_path.write_text(prompts_md, encoding="utf-8")
        if prompts_json:
            json_path = self.project_dir / "prompts.json"
            json_path.write_text(json.dumps(prompts_json, ensure_ascii=False, indent=2), encoding="utf-8")
        return md_path

    def load_prompts(self) -> str:
        path = self.project_dir / "prompts.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def get_audio_path(self, filename: str) -> Path:
        return self.audio_dir / filename

    def save_packaging(self, packaging_md: str) -> Path:
        path = self.project_dir / "packaging.md"
        path.write_text(packaging_md, encoding="utf-8")
        return path

    def load_packaging(self) -> str:
        path = self.project_dir / "packaging.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def save_titles(self, text: str) -> Path:
        path = self.project_dir / "titles.txt"
        path.write_text(text, encoding="utf-8")
        return path

    def load_titles(self) -> str:
        path = self.project_dir / "titles.txt"
        if path.exists():
            return path.read_text(encoding="utf-8")
        pack = self.load_packaging()
        if pack:
            from modules.packaging_generator import PackagingGenerator
            sections = PackagingGenerator.parse_packaging(pack)
            return sections.get("titles", "")
        return ""

    def save_description(self, text: str) -> Path:
        path = self.project_dir / "description.txt"
        path.write_text(text, encoding="utf-8")
        return path

    def load_description(self) -> str:
        path = self.project_dir / "description.txt"
        if path.exists():
            return path.read_text(encoding="utf-8")
        pack = self.load_packaging()
        if pack:
            from modules.packaging_generator import PackagingGenerator
            sections = PackagingGenerator.parse_packaging(pack)
            return sections.get("description", "")
        return ""

    def save_style_dna(self, dna: Dict[str, Any]) -> Path:
        import json
        path = self.project_dir / "style_dna.json"
        path.write_text(json.dumps(dna, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def load_style_dna(self) -> Optional[Dict[str, Any]]:
        import json
        path = self.project_dir / "style_dna.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    def save_outline(self, outline_text: str) -> Path:
        path = self.project_dir / "outline.txt"
        path.write_text(outline_text, encoding="utf-8")
        return path

    def load_outline(self) -> str:
        path = self.project_dir / "outline.txt"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def save_meta(self, meta: Dict[str, Any]) -> Path:
        path = self.project_dir / "meta.json"
        existing = self.load_meta()
        existing.update(meta)
        path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def load_meta(self) -> Dict[str, Any]:
        path = self.project_dir / "meta.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}
