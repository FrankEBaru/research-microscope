#!/usr/bin/env python3
"""Pruebas unitarias del pipeline de datos (sin red). `python3 -m unittest scripts/test_pipeline.py`"""
import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import build_data as bd  # noqa

T = lambda v: {"t": "text", "v": v}
SP = T(" ")


class Sentences(unittest.TestCase):
    def test_no_pierde_nodos(self):
        ins = [T("We"), SP, T("use"), SP, T("Fig."), SP, T("2"), SP, T("here."), SP, T("Then"), SP, T("et"), SP, T("al."), SP, {"t": "cite", "keys": ["a"]}, SP, T("said."), SP, T("Next.")]
        s = bd.split_sentences(ins)
        self.assertEqual(sum(s, []), ins)
        self.assertEqual(len(s), 3)  # «Fig.» y «al.» no cortan

    def test_nota_pegada_al_punto(self):
        ins = [T("end."), {"t": "note", "blocks": []}, SP, T("Start")]
        s = bd.split_sentences(ins)
        self.assertEqual(sum(s, []), ins)
        self.assertEqual(s[0][-2]["t"], "note")


class Math(unittest.TestCase):
    def test_label_y_acentos(self):
        self.assertEqual(bd.clean_math(r"a=b\label{eq:x}"), "a=b")
        self.assertEqual(bd.clean_math(r"\hat \mathbb{E}_D"), r"\hat{\mathbb{E}}_D")

    def test_text_to_inlines_con_matematica(self):
        ins = bd.text_to_inlines("the $N_\\text{opt}$ scales")
        self.assertEqual([x["t"] for x in ins if x["t"] == "math"], ["math"])
        self.assertEqual(bd.plain(ins), "the $N_\\text{opt}$ scales")


class Latex(unittest.TestCase):
    def test_captions_sin_lineas_en_blanco(self):
        t = "\\caption{uno\n\ndos} fuera\n\nparrafo"
        out = bd.fix_captions(t)
        self.assertIn("uno dos", out)
        self.assertIn("fuera\n\nparrafo", out)

    def test_numeracion_y_aplanado(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "main.tex").write_text("\\begin{document}\\input{sec}\n% \\begin{equation}comentada\\end{equation}\n\\begin{equation}a=b\\end{equation}\\end{document}")
            (d / "sec.tex").write_text("\\begin{equation}x=y\\end{equation}\\begin{equation}z\\nonumber\\end{equation}")
            out = bd.flatten_and_number(d, "main.tex")
            t = (d / out).read_text()
            self.assertIn("\\tag{1}x=y", t)
            self.assertIn("\\tag{2}a=b", t)
            self.assertNotIn("comentada", t)
            self.assertNotIn("\\tag{3}", t)  # \nonumber respeta

    def test_no_numera_si_numberwithin(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "m.tex").write_text("\\numberwithin{equation}{section}\\begin{equation}a\\end{equation}")
            self.assertNotIn("\\tag", (d / bd.flatten_and_number(d, "m.tex")).read_text())


class Anclas(unittest.TestCase):
    P = {"arxivId": "x", "blocks": [
        {"kind": "p", "id": "b0", "abs": True, "inlines": [T("alpha beta gamma")]},
        {"kind": "p", "id": "b1", "inlines": [T("alpha beta gamma delta")]},
        {"kind": "p", "id": "b2", "inlines": [T("unico")]}]}

    def test_unica(self):
        self.assertEqual(bd.resolve(self.P, "unico", "t")["blockId"], "b2")

    def test_abstract_gana_si_repite(self):
        self.assertEqual(bd.resolve(self.P, "alpha beta", "t")["blockId"], "b0")

    def test_falla_si_no_existe(self):
        with self.assertRaises(SystemExit):
            bd.resolve(self.P, "no esta", "t")


class Bibliografia(unittest.TestCase):
    def test_bbl_autor_ano(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "x.bbl").write_text("\\begin{thebibliography}{1}\n\\bibitem[{Kaplan et~al.(2020)Kaplan, McCandlish, Henighan}]{k20}\nKaplan, J.\n\\newblock Scaling laws.\n\\end{thebibliography}")
            refs, labels = bd.bibliography(d)
            self.assertEqual(labels["k20"], "Kaplan et al., 2020")
            self.assertIn("Scaling laws", refs["k20"])


class Contenido(unittest.TestCase):
    def test_contenido_curado_bien_formado(self):
        c = Path(__file__).parent.parent / "content"
        m = json.loads((c / "map.json").read_text())
        for q in m["questions"]:
            ids = {p["id"] for cl in q["clusters"] for p in cl["papers"]}
            self.assertEqual(set(q["layout"]["pos"]), ids, q["id"])
            for e in q["layout"]["edges"]:
                self.assertIn(e["from"], ids); self.assertIn(e["to"], ids)
                self.assertIn(e["kind"], {"bibliografia", "abstract", "curado"})
            for cl in q["clusters"]:  # los exponentes del deslizador deben estar en la frase citada (sin deriva)
                t = cl.get("tension")
                if t:
                    self.assertIn(str(t["exponents"]["a"]), t["numbers"]["quote"])
                    self.assertIn("0.50", t["numbers"]["quote"]); self.assertEqual(t["exponents"]["b"], 0.5)


if __name__ == "__main__":
    unittest.main()
