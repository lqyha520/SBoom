"""在候选镜像内离线重放历史故障；stdin 为固定样本，不调用外部模型。"""
import json
import sys

from app.services.generation_results import _take_questions, normalize_reading_passage
from app.services.model_json import ModelFormatError, extract_json
from app.services.question_qc import question_issue


def evaluate(cases):
    results = []
    for case in cases:
        if case['kind'] == 'passage_match':
            passed = (normalize_reading_passage(case['original']) == normalize_reading_passage(case['returned'])) == case['equivalent']
        elif case['kind'] == 'normalized_question':
            kept, rejected = _take_questions({'questions': [case['question']]}, case['game_type'], 1)
            passed = (not kept and bool(rejected)) if case['reject'] else (
                len(kept) == 1 and not rejected and all(kept[0].get(key) == value for key, value in case['expected'].items())
            )
        elif case['kind'] == 'question':
            actual = bool(question_issue(case['question'], **case.get('options', {})))
            passed = actual == case['reject']
        else:
            try:
                parsed = extract_json(case['text'], expected_key='questions')
                passed = parsed == case.get('expected') and not case.get('error')
            except ModelFormatError as error:
                passed = error.reason == case.get('error')
        results.append({'id': case['id'], 'passed': passed})
    return {'passed': all(item['passed'] for item in results), 'cases': results}


if __name__ == '__main__':
    print(json.dumps(evaluate(json.load(sys.stdin)['cases'])))
