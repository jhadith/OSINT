"""hash_archivo solo abre datasets regulares dentro de las carpetas permitidas (sin path traversal)."""
import hashlib

import pytest

from motor.hbvf import almacen


def test_hash_de_un_dataset_permitido(tmp_path):
    f = tmp_path / "citas.csv"
    f.write_bytes(b"a,b\n1,2\n")
    assert almacen.hash_archivo(f) == hashlib.sha256(b"a,b\n1,2\n").hexdigest()


def test_rechaza_rutas_fuera_de_las_carpetas_permitidas(monkeypatch, tmp_path):
    monkeypatch.setattr(almacen, "_raices_permitidas", lambda: [tmp_path / "datos"])
    (tmp_path / "datos").mkdir()
    fuera = tmp_path / "secreto.txt"
    fuera.write_text("x")
    with pytest.raises(ValueError, match="fuera de las carpetas"):
        almacen.hash_archivo(tmp_path / "datos" / ".." / "secreto.txt")


def test_rechaza_carpetas_y_archivos_inexistentes(tmp_path):
    with pytest.raises(ValueError, match="No es un archivo"):
        almacen.hash_archivo(tmp_path)
    with pytest.raises(FileNotFoundError):
        almacen.hash_archivo(tmp_path / "no_existe.csv")


def test_raices_incluyen_las_carpetas_configuradas(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTINEL_DATOS", str(tmp_path / "datos"))
    monkeypatch.setenv("SENTINEL_ESTADO", str(tmp_path / "estado"))
    raices = almacen._raices_permitidas()
    assert (tmp_path / "datos").resolve() in raices and (tmp_path / "estado").resolve() in raices
