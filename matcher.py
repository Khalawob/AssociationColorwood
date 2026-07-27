import json
import re
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher


@dataclass
class MatchResult:
    board_id: str | None
    confidence: float
    status: str
    candidates: list[tuple[str, int]]
    ambiguous_with: list[str]
    corrections: list[tuple[str, str, float]] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)


def _normalise_squash(word: str) -> str:
    return re.sub(r'[^a-z0-9]', '', word.lower())


def _normalise_spaced(word: str) -> str:
    return ' '.join(word.lower().split())


class Matcher:
    def __init__(self, boards_path: str):
        with open(boards_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self._boards = data['boards']
        self._index: dict[str, list[int]] = {}
        self._variants: dict[int, set[str]] = {}
        self._opening_sig: dict[int, frozenset[str]] = {}
        self._sig_groups: dict[frozenset[str], list[int]] = {}

        for i, board in enumerate(self._boards):
            self._variants[i] = {v for _, v in board['occurrences']}

            opening_words = []
            for group in board['groups']:
                for word in group['words']:
                    sq = _normalise_squash(word)
                    sp = _normalise_spaced(word)
                    self._index.setdefault(sq, []).append(i)
                    if sp != sq:
                        self._index.setdefault(sp, []).append(i)
                    if group.get('depth') == 0:
                        opening_words.append(sq)

            sig = frozenset(opening_words)
            self._opening_sig[i] = sig
            self._sig_groups.setdefault(sig, []).append(i)

    def _lookup(self, word: str) -> list[int]:
        sq = _normalise_squash(word)
        hits = self._index.get(sq, [])
        if not hits:
            sp = _normalise_spaced(word)
            hits = self._index.get(sp, [])
        return hits

    def _board_vocabulary(self, board_indices: list[int]) -> dict[str, str]:
        vocab: dict[str, str] = {}
        for idx in board_indices:
            for group in self._boards[idx]['groups']:
                for word in group['words']:
                    sq = _normalise_squash(word)
                    if sq not in vocab:
                        vocab[sq] = word
        return vocab

    def _fuzzy_correct(self, word: str, vocab: dict[str, str],
                       threshold: float = 0.8) -> tuple[str, float] | None:
        sq = _normalise_squash(word)
        if sq in vocab:
            return None
        best_ratio = 0.0
        best_match = None
        for candidate in vocab:
            ratio = SequenceMatcher(None, sq, candidate).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = candidate
        if best_match and best_ratio >= threshold:
            return best_match, best_ratio
        return None

    def identify(self, visible_words: list[str],
                 variant_hint: str | None = None) -> MatchResult:
        if not visible_words:
            return MatchResult(None, 0.0, 'none', [], [])

        votes: Counter[int] = Counter()
        board_matched_words: dict[int, set[str]] = {}
        unmatched_words: list[str] = []

        for word in visible_words:
            sq = _normalise_squash(word)
            hits = self._lookup(word)
            if hits:
                for idx in hits:
                    votes[idx] += 1
                    board_matched_words.setdefault(idx, set()).add(sq)
            else:
                unmatched_words.append(word)

        if not votes and not unmatched_words:
            return MatchResult(None, 0.0, 'none', [], [])

        corrections: list[tuple[str, str, float]] = []
        still_unmatched: list[str] = []

        if votes and unmatched_words:
            top_indices = [idx for idx, _ in votes.most_common(5)]
            vocab = self._board_vocabulary(top_indices)
            for word in unmatched_words:
                result = self._fuzzy_correct(word, vocab)
                if result:
                    corrected, ratio = result
                    corrections.append((word, vocab[corrected], ratio))
                    hits = self._index.get(corrected, [])
                    for idx in hits:
                        votes[idx] += 1
                        board_matched_words.setdefault(idx, set()).add(corrected)
                else:
                    still_unmatched.append(word)
        else:
            still_unmatched = unmatched_words

        if not votes:
            return MatchResult(None, 0.0, 'none', [], [])

        ranked = votes.most_common()
        top_vote = ranked[0][1]

        if top_vote < 3:
            return MatchResult(None, 0.0, 'none', [], [])

        tied = [idx for idx, v in ranked if v == top_vote]

        if variant_hint and len(tied) > 1:
            match = [idx for idx in tied if variant_hint in self._variants[idx]]
            no_match = [idx for idx in tied if variant_hint not in self._variants[idx]]
            tied = match + no_match

        winner_idx = tied[0]
        winner_id = self._boards[winner_idx]['id']
        winner_votes = top_vote
        confidence = winner_votes / len(visible_words)

        winner_words = board_matched_words.get(winner_idx, set())
        ambiguous_ids = []
        for idx in tied[1:]:
            other_words = board_matched_words.get(idx, set())
            if other_words == winner_words:
                ambiguous_ids.append(self._boards[idx]['id'])

        candidates = [(self._boards[idx]['id'], v) for idx, v in ranked[:10]]

        second_vote = ranked[1][1] if len(ranked) > 1 else 0
        margin = top_vote - second_vote

        if ambiguous_ids:
            status = 'ambiguous'
        elif margin < 2 or confidence < 0.5:
            status = 'weak'
        else:
            status = 'confident'

        return MatchResult(
            board_id=winner_id,
            confidence=confidence,
            status=status,
            candidates=candidates,
            ambiguous_with=ambiguous_ids,
            corrections=corrections,
            unmatched=still_unmatched,
        )
