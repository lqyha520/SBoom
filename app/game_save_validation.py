"""云存档的结构边界；具体关卡、题目答案和恢复规则仍由各游戏校验。"""

from typing import Any, TypeGuard


def integer(value, maximum=1_000_000):
    return type(value) is int and 0 <= value <= maximum


def numbers(value, keys, maximum=1_000_000):
    return isinstance(value, dict) and all(integer(value.get(key), maximum) for key in keys)


def sequence(value: object, maximum=64) -> TypeGuard[list[Any]]:
    return isinstance(value, list) and len(value) <= maximum


def strings(value, maximum=64):
    return sequence(value, maximum) and all(isinstance(item, str) for item in value)


def valid_progress(game_id: str, value: dict) -> bool:
    if type(value.get('version')) is not int or value['version'] != 1:
        return False
    if game_id == 'little-shop':
        return (value.get('difficulty') in ('count', 'total', 'change')
                and value.get('stage') in ('packing', 'total', 'change', 'served', 'closed')
                and numbers(value, ('day', 'customer', 'cash', 'revenue', 'profit', 'mistakes', 'hints', 'upgrades', 'lifetimeServed'))
                and value['day'] >= 1 and value['customer'] <= 3 and value['upgrades'] <= 2
                and all(numbers(value.get(key), ('apple', 'banana', 'pear', 'orange'), 12) for key in ('bag', 'stock')))
    if game_id == 'robot-maze':
        stars, hints, program = value.get('stars'), value.get('hints'), value.get('program')
        if not (sequence(stars, 256) and stars and all(integer(n, 3) for n in stars)
                and sequence(hints, 256) and len(hints) == len(stars) and all(integer(n) for n in hints)
                and integer(value.get('level'), len(stars) - 1) and sequence(program, 24)):
            return False
        commands = ('forward', 'left', 'right')
        return all(isinstance(item, dict) and (item.get('type') in commands or (
            item.get('type') == 'repeat' and integer(item.get('count'), 4) and item['count'] >= 2
            and sequence(item.get('body'), 6) and all(command in commands for command in item['body']))) for item in program)

    fields = {
        'rocket-math': ('flight', 'totalCorrect', 'flights'),
        'fraction-pizza': ('flight', 'totalCorrect', 'flights'),
        'memory-match': ('round', 'totalMatches', 'rounds'),
        'poem-order': ('round', 'totalPoems', 'rounds'),
        'word-spell': ('round', 'totalWords', 'rounds'),
        'idiom-fill': ('round', 'totalCorrect', 'rounds'),
        'word-market': ('round', 'totalCorrect', 'rounds'),
        'clock-town': ('round', 'totalCorrect', 'rounds'),
    }
    if game_id not in fields:
        return False
    round_key, total, rounds = fields[game_id]
    difficulties = ('cozy', 'focus', 'master') if game_id == 'memory-match' else (
        ('starter', 'explorer', 'pilot') if game_id == 'rocket-math' else ('starter', 'explorer', 'master'))
    current = value.get(round_key)
    if not (value.get('difficulty') in difficulties and numbers(value, (total, rounds))
            and numbers(value.get('best'), difficulties, 3) and isinstance(current, dict)
            and type(current.get('version')) is int and current['version'] == 1
            and current.get('difficulty') == value['difficulty'] and type(current.get('finished')) is bool):
        return False
    if game_id == 'memory-match':
        cards = current.get('cards')
        return (sequence(cards, 64) and bool(cards) and all(isinstance(card, dict)
                    and integer(card.get('id'), 63) and isinstance(card.get('pairId'), str)
                    and card.get('face') in ('expression', 'answer') and isinstance(card.get('text'), str) for card in cards)
                and numbers(current, ('moves',)) and sequence(current.get('flipped'), 2)
                and all(integer(n, len(cards) - 1) for n in current['flipped']) and strings(current.get('matched')))
    questions = current.get('questions')
    if not (sequence(questions) and bool(questions) and all(isinstance(question, dict) for question in questions)
            and integer(current.get('index'), len(questions) - 1) and numbers(current, ('correct', 'mistakes'))):
        return False
    if game_id in ('poem-order', 'word-spell'):
        text_field = 'text' if game_id == 'poem-order' else 'letter'
        id_field = 'poemId' if game_id == 'poem-order' else 'wordId'
        return (type(current.get('solved')) is bool and strings(current.get('selected')) and numbers(current, ('hints',))
                and all(isinstance(question.get(id_field), str) and strings(question.get('answer'))
                        and sequence(question.get('tiles')) and all(isinstance(tile, dict)
                            and isinstance(tile.get('id'), str) and isinstance(tile.get(text_field), str)
                            for tile in question['tiles']) for question in questions))
    answered = current.get('answered')
    answer_type = int if game_id == 'rocket-math' else str
    if 'answered' not in current or answered is not None and type(answered) is not answer_type:
        return False
    for question in questions:
        options = question.get('options')
        if not sequence(options) or not options or not all(type(option) is answer_type for option in options):
            return False
        if game_id == 'rocket-math' and not (numbers(question, ('left', 'right', 'answer'))
                and question.get('operator') in ('+', '-', '×') and isinstance(question.get('expression'), str)):
            return False
        if game_id == 'fraction-pizza' and not (numbers(question, ('total', 'shaded')) and isinstance(question.get('answer'), str)):
            return False
        if game_id in ('idiom-fill', 'word-market') and not isinstance(question.get('idiomId' if game_id == 'idiom-fill' else 'wordId'), str):
            return False
        if game_id == 'clock-town' and not (numbers(question, ('hour', 'minute')) and isinstance(question.get('answer'), str)):
            return False
    return True
