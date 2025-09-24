#!/usr/bin/env python3
import argparse
import os
import re
from pathlib import Path
import sys

try:
    import chess
except ImportError:
    print("python-chess not installed; please install it.", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[2]
STATE_FILE = ROOT / 'chess' / 'state.txt'
README_FILE = ROOT / 'README.md'

BOARD_START = '<!-- CHESS:START -->'
BOARD_END = '<!-- CHESS:END -->'

PIECES = {
    chess.PAWN:   {'w': 'P', 'b': 'p'},
    chess.KNIGHT: {'w': 'N', 'b': 'n'},
    chess.BISHOP: {'w': 'B', 'b': 'b'},
    chess.ROOK:   {'w': 'R', 'b': 'r'},
    chess.QUEEN:  {'w': 'Q', 'b': 'q'},
    chess.KING:   {'w': 'K', 'b': 'k'},
}

IMG_BASE = 'https://raw.githubusercontent.com/timburgan/timburgan/master/chess_images'
IMG_MAP = {
    'P': f'{IMG_BASE}/P.png', 'p': f'{IMG_BASE}/p.png',
    'N': f'{IMG_BASE}/N.png', 'n': f'{IMG_BASE}/n.png',
    'B': f'{IMG_BASE}/B.png', 'b': f'{IMG_BASE}/b.png',
    'R': f'{IMG_BASE}/R.png', 'r': f'{IMG_BASE}/r.png',
    'Q': f'{IMG_BASE}/Q.png', 'q': f'{IMG_BASE}/q.png',
    'K': f'{IMG_BASE}/K.png', 'k': f'{IMG_BASE}/k.png',
    '.': f'{IMG_BASE}/blank.png',
}


def read_state():
    if not STATE_FILE.exists():
        board = chess.Board()
        return board
    content = STATE_FILE.read_text(encoding='utf-8').splitlines()
    fen_line = next((l for l in content if l.startswith('FEN:')), None)
    fen = fen_line.split('FEN:')[1].strip() if fen_line else chess.STARTING_FEN
    return chess.Board(fen)


def write_state(board: chess.Board):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    text = f"FEN: {board.fen()}\nTURN: {'w' if board.turn == chess.WHITE else 'b'}\n"
    STATE_FILE.write_text(text, encoding='utf-8')


def uci_from_title(move_str: str) -> str:
    if not move_str:
        return ''
    move_str = move_str.strip().lower()
    # Expecting like: e2e4, g1f3, e7e8q, etc.
    if re.fullmatch(r"[a-h][1-8][a-h][1-8][qrbn]?", move_str):
        return move_str
    return ''


def apply_move_if_any(board: chess.Board, move_uci: str, actor: str) -> str:
    if not move_uci:
        return ''
    try:
        move = chess.Move.from_uci(move_uci)
    except ValueError:
        return ''
    if move not in board.legal_moves:
        return ''
    board.push(move)
    algebraic = board.peek().uci()
    return algebraic


def render_board(board: chess.Board) -> str:
    # Render a markdown table using piece image URLs
    lines = []
    lines.append('|   | A | B | C | D | E | F | G | H |')
    lines.append('| - | - | - | - | - | - | - | - | - |')
    for rank in range(8, 0, -1):
        row = [str(rank)]
        for file in range(1, 9):
            square = chess.square(file - 1, rank - 1)
            piece = board.piece_at(square)
            key = '.'
            if piece:
                key = PIECES[piece.piece_type]['w' if piece.color == chess.WHITE else 'b']
            row.append(f"![]({IMG_MAP[key]})")
        lines.append('| ' + ' | '.join(row) + ' |')
    return '\n'.join(lines)


def legal_move_links(board: chess.Board, repo: str) -> str:
    # Show a compact moves box: list FROM squares with TO links
    by_from = {}
    for mv in board.legal_moves:
        src = chess.square_name(mv.from_square).upper()
        dst = chess.square_name(mv.to_square).upper()
        by_from.setdefault(src, []).append(dst)
    # Build markdown table with issue links
    base = f"https://github.com/{repo}/issues/new?title="
    lines = ['| FROM | TO - _click a link_ |', '| ---- | -- |']
    # Only show up to, say, 20 sources to keep compact
    for src in sorted(by_from.keys())[:20]:
        dsts = by_from[src]
        links = []
        for dst in sorted(dsts):
            uci = src.lower() + dst.lower()
            url = base + f"chess%7Cmove%7C{uci}%7Cnull" + "&body=Just+push+%27Submit+new+issue%27."
            links.append(f"[{dst}]({url})")
        lines.append(f"| **{src}** | " + ' , '.join(links) + ' |')
    return '\n'.join(lines)


def ensure_markers(readme: str) -> str:
    if BOARD_START in readme and BOARD_END in readme:
        return readme
    block = (
        f"{BOARD_START}\n"
        f"## Community Chess\n\n"
        f"This is a community chess board. Click a move in the box to open an issue that updates the board.\n\n"
        f"\n{BOARD_END}\n"
    )
    # Insert under top heading and before breakout picture if possible
    if '<picture>' in readme:
        idx = readme.index('<picture>')
        return readme[:idx] + block + readme[idx:]
    else:
        # Put near the top after first heading
        return block + '\n' + readme


def update_readme(board_md: str, moves_md: str, turn_text: str):
    readme = README_FILE.read_text(encoding='utf-8')
    readme = ensure_markers(readme)
    # safer replacement by using regex span between markers
    import re as _re
    pattern = _re.compile(_re.escape(BOARD_START) + r"[\s\S]*?" + _re.escape(BOARD_END))
    section = (
        f"{BOARD_START}\n"
        f"## Community Chess\n\n"
        f"**Game status:** It's {'White' if 'WHITE' in turn_text else 'Black'}'s turn.\n\n"
        f"{board_md}\n\n"
        f"### Moves box\n\n"
        f"{moves_md}\n\n"
        f"{BOARD_END}"
    )
    new_readme = pattern.sub(section, readme)
    README_FILE.write_text(new_readme, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--move', default='', help='UCI move like e2e4')
    parser.add_argument('--actor', default='anonymous', help='GitHub user who made the move')
    args = parser.parse_args()

    repo = os.getenv('GITHUB_REPOSITORY', '') or 'CodingHusk3y/CodingHusk3y'

    board = read_state()
    applied = apply_move_if_any(board, uci_from_title(args.move), args.actor)
    write_state(board)

    board_md = render_board(board)
    moves_md = legal_move_links(board, repo)
    turn_text = 'WHITE' if board.turn else 'BLACK'

    update_readme(board_md, moves_md, turn_text)

if __name__ == '__main__':
    main()
