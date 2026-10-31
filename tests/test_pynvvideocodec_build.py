import hashlib
import importlib.util
from pathlib import Path
import tempfile
import shlex
import unittest
import zipfile
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/build_pynvvideocodec.py"


class BindingBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("binding_build", SCRIPT)
        cls.builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.builder)

    def test_cmake_paths_with_spaces_are_passed_only_once(self):
        args = self.builder.parse_args([
            "--cmake-arg=-DCUDAToolkit_ROOT=C:/Program Files/CUDA/v12.6",
            "--pybind11-source-dir", "build/deps with spaces/pybind11",
        ])
        with patch.object(self.builder.shutil, "which", return_value="C:/MSVC/cl.exe"):
            env = self.builder.build_environment(args, {"PATH": "original", "CMAKE_ARGS": "-DOLD=ON"})
        self.assertNotIn("CMAKE_ARGS", env)
        flags = shlex.split(env["SKBUILD_CONFIGURE_OPTIONS"])
        self.assertEqual(flags.count("-DCUDAToolkit_ROOT=C:/Program Files/CUDA/v12.6"), 1)
        self.assertIn("-DOLD=ON", flags)
        self.assertTrue(any(flag.startswith("-DFETCHCONTENT_SOURCE_DIR_PYBIND11=")
                            and "deps with spaces" in flag for flag in flags))
        self.assertEqual(env["CMAKE_GENERATOR"], "Ninja Multi-Config")

    def test_rejects_wrong_archive_before_extracting(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "wrong.zip"
            archive.write_bytes(b"wrong version")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                self.builder.prepare(archive, root / "work")
            self.assertFalse((root / "work").exists())

    def test_rejects_archive_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "escape.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("../outside", "bad")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            with patch.object(self.builder, "ARCHIVE_SHA256", digest):
                with self.assertRaises(ValueError):
                    self.builder.prepare(archive, root / "work")
            self.assertFalse((root / "outside").exists())

    def test_real_archive_patch_and_repeated_preparation(self):
        archive = ROOT / "PyNvVideoCodec_2.2.2.zip"
        if not archive.exists():
            self.skipTest("공식 소스 ZIP이 없습니다.")
        with tempfile.TemporaryDirectory() as temp:
            source = self.builder.prepare(archive, Path(temp) / "work")
            binding = (source / "src/PyNvVideoCodec/src/PyNvDecoder.cpp").read_text(encoding="utf-8")
            self.assertIn('"GetLockedFrameWithPTS"', binding)
            self.assertIn("dec->GetLockedFrame(&timestamp)", binding)
            self.assertIn("dec->GetLockedFrame(NULL)", binding)
            self.assertIn("2.2.2+pipeworks.1", (source / "pyproject.toml").read_text())
            self.assertEqual(source, self.builder.prepare(archive, Path(temp) / "work"))
            target = source / "src/PyNvVideoCodec/src/PyNvDecoder.cpp"
            target.write_text(binding + "\n// changed\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "변경"):
                self.builder.prepare(archive, Path(temp) / "work")


if __name__ == "__main__":
    unittest.main()
