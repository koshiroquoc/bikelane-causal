import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    summary = json.loads((root / "reports" / "release_summary.json").read_text())
    claims = summary["claims_contract"]
    print("Protected Bike Lanes and Divvy Ridership — v1.0.0")
    print(
        f"Primary estimate: {claims['phase4_effect_percent']:.1f}% "
        f"(95% CI {claims['phase4_ci_low_percent']:.1f}% to "
        f"{claims['phase4_ci_high_percent']:.1f}%)"
    )
    print(claims["allowed_final_claim"])


if __name__ == "__main__":
    main()
