"""mctl-gitops#2288: the credential delivery validator holds on the real repo
and fails on mutated copies of the CWFTs.

Run: python3 tests/test_agent_credential_delivery.py
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/validate-agent-credential-delivery.py"
CWFT = REPO / "platform-gitops/argo-workflows/cluster-templates"
INV = REPO / "platform-gitops/governance/agent-credential-delivery.yaml"
SEED = ("          - name: GITHUB_TOKEN\n            valueFrom:\n              secretKeyRef:\n"
        "                name: mctl-agents-secrets\n                key: github-token\n")


def run(directory):
    return subprocess.run([sys.executable, "-I", str(SCRIPT), "--dir", str(directory), "--inventory", str(INV)],
                          capture_output=True, text=True)


def mutated(filename, old, new):
    with tempfile.TemporaryDirectory() as d:
        for f in CWFT.glob("cwft-mctl-agents-*.yaml"):
            shutil.copy(f, d)
        p = pathlib.Path(d) / filename
        text = p.read_text()
        assert old in text, (filename, old)
        p.write_text(text.replace(old, new, 1))
        return run(d)


def main():
    results = []

    def check(name, ok, detail=""):
        results.append((name, ok, detail))

    r = run(CWFT)
    check("real repo passes", r.returncode == 0, r.stderr)

    inv_file = "cwft-mctl-agents-investigate.yaml"
    r = mutated(inv_file, "          - name: GITHUB_TOKEN_FILE\n",
                SEED + "          - name: GITHUB_TOKEN_FILE\n")
    check("restored GITHUB_TOKEN seed fails naming template and variable",
          r.returncode != 0 and "run-investigator" in r.stderr and "GITHUB_TOKEN" in r.stderr
          and inv_file in r.stderr, r.stderr)

    r = mutated(inv_file, "          - name: GITHUB_TOKEN_FILE\n",
                "          - name: UNLISTED\n            valueFrom:\n              secretKeyRef:\n"
                "                name: mctl-agents-secrets\n                key: other\n"
                "          - name: GITHUB_TOKEN_FILE\n")
    check("unlisted agent secretKeyRef fails", r.returncode != 0 and "UNLISTED" in r.stderr, r.stderr)

    r = mutated("cwft-mctl-agents-run.yaml", "        defaultMode: 0440\n", "        defaultMode: 0644\n")
    check("0644 credential volume fails", r.returncode != 0 and "0440" in r.stderr, r.stderr)

    r = mutated("cwft-mctl-agents-run.yaml", "            mountPath: /var/run/gh\n            readOnly: true\n",
                "            mountPath: /var/run/gh\n")
    check("mount without readOnly fails", r.returncode != 0 and "readOnly" in r.stderr, r.stderr)

    # notify-telegram uses a non-agent image and stays env-seeded.
    text = (CWFT / "cwft-mctl-agents-run.yaml").read_text()
    check("notify-telegram secretKeyRef is allowed (non-agent image)",
          "name: notify-telegram" in text and run(CWFT).returncode == 0)

    bad = []
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            bad.append(f"{name}: {detail}")
    if bad:
        print("\n".join(bad))
        sys.exit(1)


if __name__ == "__main__":
    main()
