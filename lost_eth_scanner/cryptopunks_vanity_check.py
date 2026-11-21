#!/usr/bin/env python3
"""
CRYPTOPUNKS VANITY CHECK
=========================
For each of the 94 addresses with unclaimed CryptoPunks pendingWithdrawals,
check whether the address bears hallmarks of vanity-tool generation
(esp. Profanity tool, which is now cryptographically broken — anyone can
recover the private key in ~24h on a GPU).

If we find vanity addresses among the unclaimed-balance list, those funds
are recoverable through key cracking. This isn't a hack — it's exposing
addresses that were already broken since 2022.

Reference: 1inch research, Sept 2022
https://blog.1inch.io/a-vulnerability-disclosed-in-profanity-an-ethereum-vanity-address-tool/
"""
import json
import os
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def analyze_vanity(addr: str) -> dict:
    """Return detailed vanity profile of an address."""
    h = addr.lower().replace('0x', '')
    if len(h) != 40:
        return None

    # Leading zeros
    lz = len(h) - len(h.lstrip('0'))
    # Trailing zeros
    tz = len(h) - len(h.rstrip('0'))

    # Repeated runs
    longest_run = 1
    cur = 1
    for i in range(1, len(h)):
        if h[i] == h[i-1]:
            cur += 1
            longest_run = max(longest_run, cur)
        else:
            cur = 1

    # Dictionary words at start or end
    DICT = ['dead', 'beef', 'cafe', 'babe', 'face', 'feed', 'fade',
            'c0ff', 'bad', 'add', 'ace', 'baddad', 'b00b', 'fee5']
    starts_with_word = next((w for w in DICT if h.startswith(w)), None)
    ends_with_word = next((w for w in DICT if h.endswith(w)), None)

    # Mirror / palindrome check
    palindrome_len = 0
    for i in range(min(len(h)//2, 10)):
        if h[i] == h[-(i+1)]:
            palindrome_len += 1
        else:
            break

    # Profanity-specific: very specific character class biases
    # Profanity used GPU brute-force on a 32-bit seed
    # Result: addresses with strong vanity patterns at start/end

    # Score
    profanity_likely = False
    score = 0
    reasons = []

    if lz >= 6:
        score += lz * 5
        reasons.append(f'leading_zeros={lz}')
        profanity_likely = True
    elif lz >= 4:
        score += lz * 3
        reasons.append(f'leading_zeros={lz}')

    if tz >= 6:
        score += tz * 5
        reasons.append(f'trailing_zeros={tz}')
        profanity_likely = True
    elif tz >= 4:
        score += tz * 3
        reasons.append(f'trailing_zeros={tz}')

    if longest_run >= 6:
        score += longest_run * 4
        reasons.append(f'repeated_run={longest_run}')
        profanity_likely = True

    if starts_with_word:
        score += 20
        reasons.append(f'starts_with={starts_with_word}')
        profanity_likely = True
    if ends_with_word:
        score += 20
        reasons.append(f'ends_with={ends_with_word}')
        profanity_likely = True

    if palindrome_len >= 5:
        score += palindrome_len * 3
        reasons.append(f'palindrome={palindrome_len}')

    # Hex byte distribution: vanity addresses often have many of one digit
    counter = {}
    for c in h:
        counter[c] = counter.get(c, 0) + 1
    most_common = max(counter.values())
    if most_common >= 12:  # 30%+ of one char in a vanity addr
        score += most_common * 2
        reasons.append(f'most_common_char_count={most_common}')

    return {
        'addr': addr.lower(),
        'leading_zeros': lz,
        'trailing_zeros': tz,
        'longest_run': longest_run,
        'starts_with': starts_with_word,
        'ends_with': ends_with_word,
        'palindrome': palindrome_len,
        'most_common_char_count': most_common,
        'score': score,
        'profanity_likely': profanity_likely,
        'reasons': reasons,
    }


def main():
    cp_path = os.path.join(SCRIPT_DIR, 'results', 'cryptopunks_pending.json')
    with open(cp_path) as f:
        entries = json.load(f)

    print(f'[*] Analyzing {len(entries)} CryptoPunks unclaimed-balance addresses for vanity patterns')
    print(f'[*] Looking for Profanity-tool fingerprints (key crackable since Sept 2022)\n')

    annotated = []
    for e in entries:
        prof = analyze_vanity(e['seller'])
        if prof:
            prof['pending_eth'] = e['pending_eth']
            prof['contract'] = e.get('contract', '')
            annotated.append(prof)

    # Sort by composite: score x pending_eth (high score on big balance is most valuable)
    annotated.sort(key=lambda x: x['score'] * x['pending_eth'], reverse=True)

    print('=' * 100)
    print('  TOP VANITY-PATTERN MATCHES IN CRYPTOPUNKS UNCLAIMED LIST')
    print('=' * 100)
    print(f'{"#":>3} {"score":>5} {"pending":>10} {"address":<44}  details')
    print('-' * 100)

    profanity_hits = []
    significant = []

    for i, a in enumerate(annotated):
        if a['score'] >= 15 or a['profanity_likely']:
            print(f"{i+1:>3} {a['score']:>5} {a['pending_eth']:>10,.4f} ETH  {a['addr']}  {','.join(a['reasons'])}")
            if a['profanity_likely']:
                profanity_hits.append(a)
            if a['score'] >= 15:
                significant.append(a)

    print('\n' + '=' * 100)
    print('  STATISTICAL SUMMARY')
    print('=' * 100)
    print(f'  Total unclaimed addresses:       {len(annotated)}')
    print(f'  Profanity-likely (very vulnerable): {len(profanity_hits)}')
    print(f'  Significant vanity score (>=15):    {len(significant)}')

    print(f'\n  Distribution of leading zeros:')
    lz_dist = {}
    for a in annotated:
        lz_dist[a['leading_zeros']] = lz_dist.get(a['leading_zeros'], 0) + 1
    for lz, n in sorted(lz_dist.items()):
        print(f'    {lz} zeros: {n} addresses')

    if profanity_hits:
        print(f'\n  ★ POTENTIALLY EXPLOITABLE (Profanity-style):')
        for a in profanity_hits:
            print(f'    {a["pending_eth"]:>10,.4f} ETH  {a["addr"]}  {a["reasons"]}')

    out = os.path.join(SCRIPT_DIR, 'results', 'cryptopunks_vanity_analysis.json')
    json.dump(annotated, open(out, 'w'), indent=2)
    print(f'\n[*] Saved: {out}')

    # Bonus: histogram by char distribution
    print('\n  Most-common char distribution:')
    char_freq = {}
    for a in annotated:
        char_freq.setdefault(a['most_common_char_count'], 0)
        char_freq[a['most_common_char_count']] += 1
    for c, n in sorted(char_freq.items()):
        if n > 0:
            print(f'    most_common_char={c:>2}: {n} addresses')


if __name__ == '__main__':
    main()
