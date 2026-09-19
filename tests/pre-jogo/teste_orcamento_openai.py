#!/usr/bin/env python3
"""Regressão das travas de custo do redator OpenAI."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts import redigir_pre_jogo_openai as writer

def main():
    cfg=writer.load_provider_config()
    p=cfg["provider"]; b=cfg["budget"]
    assert p["model"]=="gpt-5.6-luna"
    assert p["max_attempts"]<=2
    assert p["max_output_tokens"]<=6000
    assert b["monthly_target_usd"]<=10
    assert b["max_articles_per_day"]<=10
    assert b["max_contract_chars"]<=20000
    cost=writer.estimate_usage_cost_usd({"usage":{"input_tokens":20000,"output_tokens":6000}},cfg)
    assert cost is not None and cost < 0.012, cost
    print(f"OK: redator econômico ativo; cenário 20k entrada/6k saída ~= US$ {cost} por chamada.")

if __name__=="__main__":
    main()
