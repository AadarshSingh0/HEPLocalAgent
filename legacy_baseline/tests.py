"""
Tests for the MadGraph tree builder.
Run with:  python -m pytest tests.py -v
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from core.tree_builder import ProcessParams, build_proc_card, build_run_card
from core.extractor    import json_to_params


def test_basic_drell_yan():
    p = ProcessParams(
        initial_state=["p", "p"],
        final_state=["e-", "e+"],
    )
    card = build_proc_card(p)
    assert "import model sm" in card
    assert "generate p p > e- e+" in card
    assert "define p = p b b~" in card
    assert "output my_process" in card


def test_ttbar_14tev():
    p = ProcessParams(
        initial_state=["p", "p"],
        final_state=["t", "t~"],
        beam_energy_gev=7000,
        nevents=50000,
        pythia8=True,
    )
    card = build_proc_card(p)
    assert "generate p p > t t~" in card

    run = build_run_card(p)
    assert "7000.0  = ebeam1" in run
    assert "50000  = nevents" in run


def test_ee_higgs():
    p = ProcessParams(
        model="sm",
        initial_state=["e-", "e+"],
        final_state=["h"],
        beam_energy_gev=125,
        beam_type="electron",
        nevents=100000,
        pythia8=True,
        delphes=True,
    )
    card = build_proc_card(p)
    assert "generate e- e+ > h" in card
    # No define p line for e+e- collision
    assert "define p" not in card

    run = build_run_card(p)
    assert "11  = lpp1" in run   # electron PDG code
    assert "125.0  = ebeam1" in run


def test_mssm_neutralino():
    p = ProcessParams(
        model="mssm",
        initial_state=["p", "p"],
        final_state=["n1", "n1"],
    )
    card = build_proc_card(p)
    assert "import model MSSM_SLHA2" in card
    assert "generate p p > n1 n1" in card


def test_extra_processes():
    p = ProcessParams(
        initial_state=["p", "p"],
        final_state=["mu-", "mu+"],
        extra_processes=["p p > ta- ta+"],
        output_dir="dilepton",
    )
    card = build_proc_card(p)
    assert "generate p p > mu- mu+" in card
    assert "add process p p > ta- ta+" in card
    assert "output dilepton" in card


def test_json_to_params():
    data = {
        "model": "sm",
        "initial_state": ["p", "p"],
        "final_state": ["z"],
        "extra_processes": [],
        "beam_energy_gev": 6500,
        "beam_type": "proton",
        "nevents": 10000,
        "output_dir": "pp_z",
        "pythia8": False,
        "delphes": False,
        "qcd_order": None,
        "qed_order": None,
    }
    p = json_to_params(data)
    assert p.model == "sm"
    assert p.final_state == ["z"]
    assert p.beam_energy_gev == 6500.0


def test_heft_higgs_gluon_fusion():
    p = ProcessParams(
        model="heft",
        initial_state=["p", "p"],
        final_state=["h"],
        output_dir="ggH",
    )
    card = build_proc_card(p)
    assert "import model heft" in card
    assert "generate p p > h" in card


if __name__ == "__main__":
    tests = [
        test_basic_drell_yan,
        test_ttbar_14tev,
        test_ee_higgs,
        test_mssm_neutralino,
        test_extra_processes,
        test_json_to_params,
        test_heft_higgs_gluon_fusion,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  ✅  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌  {t.__name__}: {e}")

    print(f"\n{passed}/{len(tests)} tests passed")
