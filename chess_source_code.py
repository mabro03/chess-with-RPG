import pygame
import copy
import random
import sys
import os
import math # 방향 벡터 계산을 위해 math 모듈 추가

# --- Pygame 초기화 ---
pygame.init()

# --- 설정 상수 (20% 확대 및 쿨타임 표시 영역 추가) ---
BOARD_SIZE = 720 # 600 * 1.2 = 720
DISPLAY_WIDTH = BOARD_SIZE + 200 # 쿨타임 표시를 위해 오른쪽 200px 추가
DISPLAY_HEIGHT = BOARD_SIZE
ROWS, COLS = 8, 8
SQUARE_SIZE = BOARD_SIZE // COLS # 720 / 8 = 90

# 색상 (RGB)
WHITE_COLOR = (238, 238, 210)
BLACK_COLOR = (118, 150, 86)
RED = (200, 50, 50)
GREEN = (50, 200, 50)
BLUE = (50, 50, 200)

# --- 사용자 지정 배경 이미지 경로 ---
# TODO: 여기에 사용하고 싶은 이미지 파일 경로를 설정하세요.
# 예시: 'assets/start_bg.png'
IMAGE_PATH = os.path.join('assets', 'start_bg.png') 

# --- 기물 클래스 ---
class Piece:
    # 12개의 기물 이미지를 메모리에 캐시하기 위한 클래스 변수
    IMAGE_CACHE = {} 

    def __init__(self, name, color, row, col):
        self.name = name
        self.color = color
        self.row = row
        self.col = col
        
        # 1. RPG 스탯 설정
        stats = {
            'King':    {'hp': 20, 'ap': 5}, 'Queen':  {'hp': 15, 'ap': 9},
            'Rook':    {'hp': 12, 'ap': 7}, 'Bishop': {'hp': 10, 'ap': 6},
            'Knight': {'hp': 9, 'ap': 6}, 'Pawn':    {'hp': 5, 'ap': 3}
        }
        self.max_hp = stats[name]['hp']
        self.hp = self.max_hp
        self.base_ap = stats[name]['ap']
        self.dmg_reduction = 0
        self.first_attack = True
        self.cooldown = 0
        
        # 퀸 특수 능력 쿨타임 설정
        if self.name == 'Queen':
            self.special_cooldown_max = 3 # 3턴 쿨타임
            self.special_cooldown = 0
        else:
            self.special_cooldown_max = 0
            self.special_cooldown = 0
        
        # 2. 이미지 로드 및 설정 (이미지 캐싱)
        symbol = {'Pawn':'P', 'Rook':'R', 'Knight':'N', 'Bishop':'B', 'Queen':'Q', 'King':'K'}[name]
        prefix = 'w' if color == 'white' else 'b'
        self.image_key = f'{prefix}{symbol}'
        
        if self.image_key not in Piece.IMAGE_CACHE:
            # 파일 경로: assets/pieces/wQ.png 와 같은 형태
            filename = os.path.join('assets', 'pieces', f'{self.image_key}.png')
            try:
                original_image = pygame.image.load(filename).convert_alpha()
                Piece.IMAGE_CACHE[self.image_key] = pygame.transform.scale(original_image, (SQUARE_SIZE, SQUARE_SIZE))
            except pygame.error as e:
                print(f"이미지 로드 실패: {filename} - {e}. 대체 이미지를 사용합니다.")
                Piece.IMAGE_CACHE[self.image_key] = None

    @property
    def image(self):
        return Piece.IMAGE_CACHE.get(self.image_key)

    @property
    def ap(self):
        if self.name == 'Pawn' and self.first_attack:
            return self.base_ap + 1
        return self.base_ap

    def draw(self, win):
        x = self.col * SQUARE_SIZE
        y = self.row * SQUARE_SIZE
        
        center_x = self.col * SQUARE_SIZE + SQUARE_SIZE // 2
        center_y = self.row * SQUARE_SIZE + SQUARE_SIZE // 2

        # 1. 이미지 그리기
        if self.image:
            win.blit(self.image, (x, y))
        else:
            # 이미지 로드 실패 시 대체 원형 표시
            color = (255, 255, 255) if self.color == 'white' else (50, 50, 50)
            pygame.draw.circle(win, color, (center_x, center_y), SQUARE_SIZE // 2 - 10)
            font = pygame.font.SysFont('arial', 12, bold=True)
            text_color = (0,0,0) if self.color == 'white' else (255,255,255)
            text = font.render(self.name[:2], True, text_color)
            win.blit(text, (center_x-10, center_y-10))

        # 2. RPG 스탯 (HP/AP) 표시
        stat_font = pygame.font.SysFont('arial', 20, bold=True)
        
        # HP (GREEN)
        hp_text = stat_font.render(str(self.hp), True, GREEN)
        hp_x = self.col * SQUARE_SIZE + 5
        hp_y = (self.row + 1) * SQUARE_SIZE - 25
        win.blit(hp_text, (hp_x, hp_y))
        
        # AP (RED)
        ap_text = stat_font.render(str(self.ap), True, RED)
        ap_rect = ap_text.get_rect(topright=((self.col + 1) * SQUARE_SIZE - 5, (self.row + 1) * SQUARE_SIZE - 25))
        win.blit(ap_text, ap_rect)

    def move(self, row, col):
        self.row = row
        self.col = col
        self.dmg_reduction = 0

# --- 게임 엔진 & AI 로직 ---
class Game:
    def __init__(self, win):
        self.win = win
        self.board = [[None for _ in range(COLS)] for _ in range(ROWS)]
        self.turn = 'white'  
        self.selected_piece = None
        self.valid_moves = []
        self.winner = None
        self._init_board()
        
        # --- 애니메이션 상태 변수 ---
        self.is_animating = False
        self.animation_piece = None
        self.animation_start_pos = None
        self.animation_target_pos = None
        self.animation_start_time = 0
        self.animation_duration = 300 # ms
        self.pending_move_data = {}
        
        # 데미지 표시 상태 변수 (r, c, damage, start_time)
        self.damage_displays = []

    def _init_board(self):
        names = ['Rook', 'Knight', 'Bishop', 'Queen', 'King', 'Bishop', 'Knight', 'Rook']
        for i in range(8):
            self.board[1][i] = Piece('Pawn', 'black', 1, i)
            self.board[6][i] = Piece('Pawn', 'white', 6, i)
            self.board[0][i] = Piece(names[i], 'black', 0, i)
            self.board[7][i] = Piece(names[i], 'white', 7, i)

    # --- 표준 체스 이동 규칙 및 슬라이딩 기물 로직 (생략) ---
    def get_valid_moves(self, piece, board_state=None):
        if board_state is None: board_state = self.board
        moves = []
        r, c = piece.row, piece.col
        
        def _get_linear_moves(r, c, directions, color):
            linear_moves = []
            for dr, dc in directions:
                for i in range(1, 8):
                    nr, nc = r + dr*i, c + dc*i
                    if 0 <= nr < 8 and 0 <= nc < 8:
                        t = board_state[nr][nc]
                        if t is None:
                            linear_moves.append((nr, nc))
                        elif t.color != color:
                            linear_moves.append((nr, nc))
                            break
                        else:
                            break
                    else:
                        break
            return linear_moves

        if piece.name == 'Pawn':
            direction = -1 if piece.color == 'white' else 1
            nr, nc = r + direction, c
            if 0 <= nr < 8 and board_state[nr][nc] is None:
                moves.append((nr, nc))
                if (piece.color == 'white' and r == 6) or (piece.color == 'black' and r == 1):
                    nr2, nc2 = r + direction * 2, c
                    if board_state[nr2][nc2] is None: moves.append((nr2, nc2))
            for dc in [-1, 1]:
                nr_cap, nc_cap = r + direction, c + dc
                if 0 <= nr_cap < 8 and 0 <= nc_cap < 8:
                    target = board_state[nr_cap][nc_cap]
                    if target and target.color != piece.color: moves.append((nr_cap, nc_cap))
            return moves
        elif piece.name == 'Rook':  
            moves.extend(_get_linear_moves(r, c, [(0,1), (0,-1), (1,0), (-1,0)], piece.color))
        elif piece.name == 'Bishop':  
            moves.extend(_get_linear_moves(r, c, [(1,1), (1,-1), (-1,1), (-1,-1)], piece.color))
        elif piece.name == 'Queen':  
            directions = [(0,1), (0,-1), (1,0), (-1,0), (1,1), (1,-1), (-1,1), (-1,-1)]
            moves.extend(_get_linear_moves(r, c, directions, piece.color))
        elif piece.name == 'Knight':
            offsets = [(r-2, c-1), (r-2, c+1), (r-1, c-2), (r-1, c+2),  
                        (r+1, c-2), (r+1, c+2), (r+2, c-1), (r+2, c+1)]
            for nr, nc in offsets:
                if 0 <= nr < 8 and 0 <= nc < 8:
                    t = board_state[nr][nc]
                    if t is None or t.color != piece.color: moves.append((nr,nc))
        elif piece.name == 'King':  
            for dr in [-1,0,1]:
                for dc in [-1,0,1]:
                    if dr==0 and dc==0: continue
                    nr, nc = r+dr, c+dc
                    if 0 <= nr < 8 and 0 <= nc < 8:
                        t = board_state[nr][nc]
                        if t is None or t.color != piece.color: moves.append((nr,nc))
                            
        return moves
        
    # --- AI의 뇌: 보드 평가 (생략: 기존 코드와 동일) ---
    def evaluate_board(self, board):
        score = 0
        for r in range(ROWS):
            for c in range(COLS):
                p = board[r][c]
                if p:
                    value = p.hp + (p.ap * 2)
                    if p.name == 'Queen': value += 15
                    if p.name == 'King': value += 100
                    if p.color == 'black': score += value
                    else: score -= value
        return score

    # --- AI 이동 (Minimax - 1-depth) ---
    def ai_move_minimax(self):
        if self.winner: return

        print("AI Thinking...")
        best_score = -float('inf')
        best_move = None
        best_piece_pos = None

        pieces = [self.board[r][c] for r in range(ROWS) for c in range(COLS)  
                  if self.board[r][c] and self.board[r][c].color == 'black']

        for piece in pieces:
            valid_moves = self.get_valid_moves(piece, self.board)
            for move in valid_moves:
                temp_board_obj = copy.deepcopy(self.board)  
                temp_piece = temp_board_obj[piece.row][piece.col]
                
                # 시뮬레이션에서는 얕은 복사가 아닌 깊은 복사된 보드를 사용해야 합니다.
                simulated_board = self.simulate_move(temp_piece, move, temp_board_obj)
                
                score = self.evaluate_board(simulated_board)
                score += random.uniform(0, 0.5)

                if score > best_score:
                    best_score = score
                    best_move = move
                    best_piece_pos = (piece.row, piece.col)

        if best_piece_pos and best_move:
            real_piece = self.board[best_piece_pos[0]][best_piece_pos[1]]
            self.selected_piece = real_piece
            self.execute_real_move(best_move[0], best_move[1])
        else:
            print("AI has no valid moves.")
            self.change_turn()

    def simulate_move(self, piece, move, board_copy):
        target_r, target_c = move
        target = board_copy[target_r][target_c]
        attacker = board_copy[piece.row][piece.col]
        
        # --- 퀸 관통 공격 시뮬레이션 로직 ---
        if target and target.color != attacker.color:
            dmg = attacker.ap + (3 if attacker.name == 'Knight' else 0)
            real_dmg = max(0, dmg - target.dmg_reduction)
            
            # 퀸 관통 공격 (쿨타임 고려)
            if attacker.name == 'Queen' and attacker.special_cooldown == 0:
                # 1. 방향 벡터 계산
                dr = 0
                dc = 0
                if target_r != piece.row:
                    dr = (target_r - piece.row) // abs(target_r - piece.row)
                if target_c != piece.col:
                    dc = (target_c - piece.col) // abs(target_c - piece.col)
                
                behind_r, behind_c = target_r + dr, target_c + dc
                
                if 0 <= behind_r < 8 and 0 <= behind_c < 8:
                    behind_target = board_copy[behind_r][behind_c]
                    if behind_target and behind_target.color != attacker.color:
                        second_dmg = attacker.ap + (3 if attacker.name == 'Knight' else 0)
                        second_real_dmg = max(0, second_dmg - behind_target.dmg_reduction)
                        behind_target.hp -= second_real_dmg
                        # 시뮬레이션에서는 쿨타임을 적용하지 않음 (단순히 이득 평가만)
                        
                        if behind_target.hp <= 0:
                            board_copy[behind_r][behind_c] = None

            target.hp -= real_dmg
            
            if target.hp <= 0:
                board_copy[target_r][target_c] = None
                board_copy[attacker.row][attacker.col] = None
                attacker.move(target_r, target_c)
                board_copy[target_r][target_c] = attacker
            
            # 공격 대상이 생존했을 경우, 공격자는 원래 위치로 돌아가므로 이동 로직 없음
        else:
            # 단순 이동
            board_copy[attacker.row][attacker.col] = None
            attacker.move(target_r, target_c)
            board_copy[target_r][target_c] = attacker
            
        # 힐/버프 적용 (생략: 기존 코드와 동일)
        if attacker.name == 'Bishop':
             for r in range(target_r-1, target_r+2):
                 for c in range(target_c-1, target_c+2):
                     if 0<=r<8 and 0<=c<8:
                         p = board_copy[r][c]
                         if p and p.color == attacker.color: p.hp = min(p.max_hp, p.hp + 3)
        if attacker.name == 'King':
             attacker.hp = min(attacker.max_hp, attacker.hp + 4)
        
        return board_copy

    # --- 애니메이션 시작 및 완료 로직 ---
    def start_attack_animation(self, piece, target_r, target_c):
        target = self.board[target_r][target_c]
        
        # 1. Damage Calculation (Main Target)
        dmg = 0
        real_dmg = 0
        if target and target.color != piece.color:
            dmg = piece.ap + (3 if piece.name == 'Knight' else 0)
            real_dmg = max(0, dmg - target.dmg_reduction)
            
        # 2. Queen's Special Attack Calculation (Secondary Target)
        behind_target = None
        second_real_dmg = 0
        
        if piece.name == 'Queen' and piece.special_cooldown == 0 and target and target.color != piece.color:
            # 1. 방향 벡터 계산
            dr = 0
            dc = 0
            if target_r != piece.row:
                dr = (target_r - piece.row) // abs(target_r - piece.row)
            if target_c != piece.col:
                dc = (target_c - piece.col) // abs(target_c - piece.col)
            
            behind_r, behind_c = target_r + dr, target_c + dc
            
            if 0 <= behind_r < 8 and 0 <= behind_c < 8:
                behind_target = self.board[behind_r][behind_c]
                
            if behind_target and behind_target.color != piece.color:
                second_dmg = piece.ap + (3 if piece.name == 'Knight' else 0)
                second_real_dmg = max(0, second_dmg - behind_target.dmg_reduction)
                
        # 3. Set Animation State
        self.is_animating = True
        self.animation_piece = piece
        self.animation_start_pos = (piece.row, piece.col)
        self.animation_target_pos = (target_r, target_c)
        self.animation_start_time = pygame.time.get_ticks()
        
        # 4. Store calculated data for post-animation execution
        self.pending_move_data = {
            'target_r': target_r,
            'target_c': target_c,
            'real_dmg': real_dmg,
            'target_piece': target,
            'behind_target': behind_target, # 퀸 능력으로 인한 두 번째 타겟
            'second_real_dmg': second_real_dmg
        }
        
    def complete_move_after_animation(self):
        now = pygame.time.get_ticks()
        piece = self.animation_piece
        data = self.pending_move_data
        r, c = data['target_r'], data['target_c']
        target = data['target_piece']
        real_dmg = data['real_dmg']
        start_r, start_c = self.animation_start_pos
        
        # Reset animation state
        self.is_animating = False
        self.animation_piece = None
        
        # 1. Combat/Attack Logic
        if target and target.color != piece.color:
            target.hp -= real_dmg
            print(f"Battle: {piece.name} -> {target.name} (DMG: {real_dmg}, Remaining HP: {target.hp})")
            
            # 데미지 숫자 표시 시작 (Main Target)
            if real_dmg > 0:
                self.damage_displays.append((r, c, -real_dmg, now))
                
            piece.first_attack = False
            
            # --- 퀸 관통 공격 처리 ---
            behind_target = data.get('behind_target')
            second_real_dmg = data.get('second_real_dmg', 0)
            
            if piece.name == 'Queen' and piece.special_cooldown == 0:
                piece.special_cooldown = piece.special_cooldown_max # 쿨타임 적용
                
                if behind_target and behind_target.color != piece.color:
                    behind_target.hp -= second_real_dmg
                    print(f"Queen Special: Pierce -> {behind_target.name} (DMG: {second_real_dmg}, Remaining HP: {behind_target.hp})")
                    
                    # 데미지 숫자 표시 시작 (Secondary Target)
                    if second_real_dmg > 0:
                        # 약간 늦게 표시
                        self.damage_displays.append((behind_target.row, behind_target.col, -second_real_dmg, now + 100)) 
                        
                    if behind_target.hp <= 0:
                        if behind_target.name == 'King':
                            self.winner = piece.color
                            print(f"\n*** GAME OVER! {self.winner.upper()} WINS! ***\n")
                        self.board[behind_target.row][behind_target.col] = None
            # --- 퀸 관통 공격 처리 끝 ---

            # 메인 타겟 처리
            if target.hp <= 0:
                if target.name == 'King':
                    self.winner = piece.color
                    print(f"\n*** GAME OVER! {self.winner.upper()} WINS! ***\n")
                
                # Attacker moves to target's square (Capture)
                self.board[start_r][start_c] = None
                piece.move(r, c)
                self.board[r][c] = piece
            else:
                # Target survives, attacker moves back to start (Attack and Return)
                pass
            
        # 2. Non-Combat Move / Move after Capture
        # 타겟이 없었거나, 아군이었거나, 타겟을 잡았을 경우 이동
        if not target or target.color == piece.color or target.hp <= 0:
            self.board[start_r][start_c] = None
            piece.move(r, c)
            self.board[r][c] = piece

        # 3. Special Ability Trigger (이동 후) - 기존 능력 유지
        if piece.name == 'Bishop':
              for nr in range(r-1, r+2):
                  for nc in range(c-1, c+2):
                      if 0<=nr<8 and 0<=nc<8:
                          p = self.board[nr][nc]
                          if p and p.color == piece.color: p.hp = min(p.max_hp, p.hp+3)
        if piece.name == 'Rook': piece.dmg_reduction = 3
        if piece.name == 'King': piece.hp = min(piece.max_hp, piece.hp + 4)
        
        self.selected_piece = None
        self.valid_moves = []
        
        if self.winner is None:  
            self.change_turn()

    # --- 실제 이동 실행 (플레이어/AI 공용) ---
    def execute_real_move(self, r, c):
        piece = self.selected_piece
        target = self.board[r][c]
        
        if target and target.color != piece.color:
             # 공격이면 애니메이션 시작
             self.start_attack_animation(piece, r, c)
        else:
             # 단순 이동 (애니메이션 없음)
             self.board[piece.row][piece.col] = None
             piece.move(r, c)
             self.board[r][c] = piece
             
             # 능력 발동
             if piece.name == 'Bishop':
                 for nr in range(r-1, r+2):
                      for nc in range(c-1, c+2):
                          if 0<=nr<8 and 0<=nc<8:
                              p = self.board[nr][nc]
                              if p and p.color == piece.color: p.hp = min(p.max_hp, p.hp+3)
             if piece.name == 'Rook': piece.dmg_reduction = 3
             if piece.name == 'King': piece.hp = min(piece.max_hp, piece.hp + 4)
             
             self.selected_piece = None
             self.valid_moves = []
             
             if self.winner is None: self.change_turn()

    def change_turn(self):
        self.turn = 'black' if self.turn == 'white' else 'white'
        
        # 쿨타임 감소: 턴이 바뀔 때마다 모든 퀸의 쿨타임이 1씩 감소
        for r in range(ROWS):
            for c in range(COLS):
                p = self.board[r][c]
                if p and p.name == 'Queen' and p.special_cooldown > 0:
                    p.special_cooldown -= 1
        print(f"Turn: {self.turn}")
        
    # --- 화면 그리기 ---
    def draw(self):
        self.win.fill((0,0,0))
        for r in range(ROWS):
            for c in range(COLS):
                color = WHITE_COLOR if (r+c)%2 == 0 else BLACK_COLOR
                # 체스 보드 영역 (BOARD_SIZE x BOARD_SIZE)만 그림
                pygame.draw.rect(self.win, color, (c*SQUARE_SIZE, r*SQUARE_SIZE, SQUARE_SIZE, SQUARE_SIZE))
        
        # 이동 가능 위치 하이라이트
        if self.selected_piece:
            s = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE))
            s.set_alpha(100)
            s.fill(BLUE)
            self.win.blit(s, (self.selected_piece.col*SQUARE_SIZE, self.selected_piece.row*SQUARE_SIZE))
            
            for r, c in self.valid_moves:
                pygame.draw.circle(self.win, (0, 255, 0), 
                                   (c*SQUARE_SIZE + SQUARE_SIZE//2, r*SQUARE_SIZE + SQUARE_SIZE//2), 10)

        # 1. Draw non-animating pieces
        animating_pieces = []
        if self.is_animating:
            animating_pieces.append(self.animation_piece)
            target = self.pending_move_data.get('target_piece')
            behind_target = self.pending_move_data.get('behind_target')
            
            if target and target.color != self.animation_piece.color:
                animating_pieces.append(target)
            if behind_target and behind_target.color != self.animation_piece.color:
                animating_pieces.append(behind_target)
                
        for r in range(ROWS):
            for c in range(COLS):
                p = self.board[r][c]
                if p and p not in animating_pieces:
                    p.draw(self.win)
        
        # 2. Draw damage numbers
        self.draw_damage_display()
        
        # 3. Draw animating piece / target
        if self.is_animating:
            self.draw_attack_animation()
            
        # 4. Draw Cooldown Display (보드 바깥 영역)
        self.draw_cooldown_display()
        
        # 5. 게임 종료 시 승자 표시
        if self.winner:
            s = pygame.Surface((DISPLAY_WIDTH, DISPLAY_HEIGHT))  
            s.set_alpha(180)  
            s.fill((0, 0, 0))  
            self.win.blit(s, (0, 0))
            
            font = pygame.font.SysFont('malgungothic', 60, bold=True)
            winner_text = "플레이어 (백색)" if self.winner == 'white' else "AI (흑색)"
            text = font.render(f"{winner_text} 승리!", True, (255, 255, 0))
            text_rect = text.get_rect(center=(BOARD_SIZE // 2, DISPLAY_HEIGHT // 2))
            
            self.win.blit(text, text_rect)
        
        pygame.display.update()

    def draw_attack_animation(self):
        elapsed = pygame.time.get_ticks() - self.animation_start_time
        progress = min(1.0, elapsed / self.animation_duration)
        
        start_r, start_c = self.animation_start_pos
        target_r, target_c = self.animation_target_pos
        piece = self.animation_piece
        target = self.pending_move_data.get('target_piece')
        
        start_x = start_c * SQUARE_SIZE + SQUARE_SIZE // 2
        start_y = start_r * SQUARE_SIZE + SQUARE_SIZE // 2
        target_x = target_c * SQUARE_SIZE + SQUARE_SIZE // 2
        target_y = target_r * SQUARE_SIZE + SQUARE_SIZE // 2
        
        current_x, current_y = start_x, start_y
        
        if target and target.color != piece.color and target.hp > 0:
            # 공격 후 복귀 애니메이션 (하스스톤 스타일)
            if progress < 0.5: # 공격
                interp = progress * 2
                current_x = start_x + (target_x - start_x) * interp
                current_y = start_y + (target_y - start_y) * interp
            else: # 복귀
                interp = (progress - 0.5) * 2
                current_x = target_x + (start_x - target_x) * interp
                current_y = target_y + (start_y - target_y) * interp
                
            # 공격 대상 기물 그리기
            target_piece_at_target_pos = self.board[target_r][target_c]
            if target_piece_at_target_pos:
                 target_piece_at_target_pos.draw(self.win)
            
        else:  
            # 단순 이동 또는 공격 후 타겟 사망 (목표 칸으로 이동)
            current_x = start_x + (target_x - start_x) * progress
            current_y = start_y + (target_y - start_y) * progress
            
        # 공격 기물 그리기
        self._draw_piece_at_pos(piece, current_x, current_y)


    def _draw_piece_at_pos(self, piece, x, y):
        # 주어진 픽셀 위치 (x, y)에 기물을 그리는 헬퍼 함수
        
        # 기물 이미지 그리기
        if piece.image:
            draw_x = int(x) - SQUARE_SIZE // 2
            draw_y = int(y) - SQUARE_SIZE // 2
            self.win.blit(piece.image, (draw_x, draw_y))
        else:
            # 이미지 없을 경우 대체 원형 표시 (생략: Piece.draw와 동일)
            pass 

        # 스탯 표시 (애니메이션 중에도 스탯이 따라다니도록)
        stat_font = pygame.font.SysFont('arial', 20, bold=True)
        
        # HP: Left bottom 
        hp_text = stat_font.render(str(piece.hp), True, GREEN)
        hp_x = int(x) - SQUARE_SIZE // 2 + 5
        hp_y = int(y) + SQUARE_SIZE // 2 - 25
        self.win.blit(hp_text, (hp_x, hp_y))
        
        # AP: Right bottom
        ap_text = stat_font.render(str(piece.ap), True, RED)
        ap_rect = ap_text.get_rect(topright=(int(x) + SQUARE_SIZE // 2 - 5, int(y) + SQUARE_SIZE // 2 - 25))
        self.win.blit(ap_text, ap_rect)

    def draw_damage_display(self):
        now = pygame.time.get_ticks()
        damage_font = pygame.font.SysFont('malgungothic', 40, bold=True)
        
        new_displays = []
        for r, c, dmg, start_time in self.damage_displays:
            elapsed = now - start_time
            if elapsed < 1000: # 1초간 표시
                progress = elapsed / 1000.0
                
                # Fade out (투명도)
                alpha = int(255 * (1.0 - progress))
                
                # Move up (40 픽셀 위로 이동)
                offset_y = int(progress * -40) 
                
                # 위치 (타겟 칸 중앙)
                center_x = c * SQUARE_SIZE + SQUARE_SIZE // 2
                center_y = r * SQUARE_SIZE + SQUARE_SIZE // 2
                
                # 텍스트 렌더링
                text_surface = damage_font.render(str(abs(dmg)), True, RED)
                text_surface.set_alpha(alpha)
                
                text_rect = text_surface.get_rect(center=(center_x, center_y + offset_y))
                self.win.blit(text_surface, text_rect)
                
                new_displays.append((r, c, dmg, start_time))
            
        self.damage_displays = new_displays
        
    def draw_cooldown_display(self):
        cooldown_font = pygame.font.SysFont('malgungothic', 24, bold=True)
        
        # 보드 경계선 밖의 시작 위치
        x_offset = BOARD_SIZE + 20  
        y_start = 50
        line_height = 40
        
        self.win.blit(cooldown_font.render("--- 쿨타임 정보 (퀸) ---", True, (255, 255, 255)), (x_offset, y_start))
        y_start += line_height * 1.5
        
        queen_count = 0
        for r in range(ROWS):
            for c in range(COLS):
                p = self.board[r][c]
                if p and p.name == 'Queen':
                    queen_count += 1
                    color_name = "백색" if p.color == 'white' else "흑색"
                    cooldown_status = str(p.special_cooldown) if p.special_cooldown > 0 else "Ready"
                    status_color = GREEN if p.special_cooldown == 0 else RED
                    
                    text = f"{color_name} 퀸: {cooldown_status}"
                    self.win.blit(cooldown_font.render(text, True, status_color), (x_offset, y_start))
                    y_start += line_height
                    
        if queen_count == 0:
            self.win.blit(cooldown_font.render("퀸 없음", True, (150, 150, 150)), (x_offset, y_start))


# --- 초기화면 관련 함수 (배경 이미지 로드 추가) ---
def draw_start_screen(win):
    """시작 화면을 그리고 '게임 시작' 버튼 영역을 반환합니다."""
    
    # 1. 배경 이미지 로드 및 그리기
    try:
        # 이미지를 화면 크기에 맞게 로드 및 크기 조정
        background_image = pygame.image.load(IMAGE_PATH).convert()
        background_image = pygame.transform.scale(background_image, (DISPLAY_WIDTH, DISPLAY_HEIGHT))
        win.blit(background_image, (0, 0))
    except pygame.error:
        print(f"Warning: 배경 이미지 로드 실패 - {IMAGE_PATH}. 기본 배경을 사용합니다.")
        win.fill((30, 30, 30)) # 기본 배경 (어두운 회색)
    except FileNotFoundError:
        print(f"Warning: 배경 이미지 파일 없음 - {IMAGE_PATH}. 기본 배경을 사용합니다.")
        win.fill((30, 30, 30))
        
    # 2. 가독성을 위한 오버레이 (반투명 검정색)
    overlay = pygame.Surface((DISPLAY_WIDTH, DISPLAY_HEIGHT))
    overlay.set_alpha(150) # 투명도 설정 (0: 투명, 255: 불투명)
    overlay.fill((0, 0, 0))
    win.blit(overlay, (0, 0))

    # 3. 제목 표시
    title_font = pygame.font.SysFont('malgungothic', 72, bold=True)
    subtitle_font = pygame.font.SysFont('malgungothic', 36)
    
    title_text = title_font.render("RPG 체스", True, (255, 255, 255))
    subtitle_text = subtitle_font.render("특수 능력과 스탯을 가진 체스", True, (150, 150, 150))
    
    title_rect = title_text.get_rect(center=(DISPLAY_WIDTH // 2, DISPLAY_HEIGHT // 2 - 150))
    subtitle_rect = subtitle_text.get_rect(center=(DISPLAY_WIDTH // 2, DISPLAY_HEIGHT // 2 - 80))
    
    win.blit(title_text, title_rect)
    win.blit(subtitle_text, subtitle_rect)

    # 4. '게임 시작' 버튼 영역
    button_width, button_height = 250, 80
    button_x = DISPLAY_WIDTH // 2 - button_width // 2
    button_y = DISPLAY_HEIGHT // 2 + 50
    button_rect = pygame.Rect(button_x, button_y, button_width, button_height)
    
    # 버튼 그리기
    pygame.draw.rect(win, GREEN, button_rect, border_radius=15)
    
    # 버튼 텍스트
    button_font = pygame.font.SysFont('malgungothic', 40, bold=True)
    button_text = button_font.render("게임 시작", True, (0, 0, 0))
    text_rect = button_text.get_rect(center=button_rect.center)
    win.blit(button_text, text_rect)
    
    pygame.display.update()
    
    return button_rect


def main():
    win = pygame.display.set_mode((DISPLAY_WIDTH, DISPLAY_HEIGHT))
    pygame.display.set_caption("Chess RPG with Special Abilities")
    clock = pygame.time.Clock()
    
    # 1. 메인 메뉴 루프
    in_menu = True
    while in_menu:
        clock.tick(60)
        start_button_rect = draw_start_screen(win) # 시작 화면 그리기 및 버튼 위치 반환
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            
            if event.type == pygame.MOUSEBUTTONDOWN:
                pos = pygame.mouse.get_pos()
                # '게임 시작' 버튼 클릭 확인
                if start_button_rect.collidepoint(pos):
                    in_menu = False # 메뉴 종료, 게임 루프로 진입
                    print("Game Starting...")
                    
    # 2. 게임 플레이 루프
    game = Game(win) # 버튼 클릭 후 게임 객체 생성
    run = True
    while run:
        clock.tick(60)
        
        now = pygame.time.get_ticks()
        
        # 1. Animation Completion Check
        if game.is_animating:
            if now - game.animation_start_time >= game.animation_duration:
                game.complete_move_after_animation()
            game.draw()
            continue
        
        # 2. AI Turn 
        if game.turn == 'black' and game.winner is None:
            pygame.time.delay(500)
            game.ai_move_minimax()
            continue 
        
        # 3. Player Turn & Event Handling
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                run = False
            
            if event.type == pygame.MOUSEBUTTONDOWN and game.turn == 'white' and game.winner is None:
                pos = pygame.mouse.get_pos()
                r, c = pos[1]//SQUARE_SIZE, pos[0]//SQUARE_SIZE
                
                # 마우스 클릭이 보드 영역 안인지 확인
                if c < COLS:
                    clicked_piece = game.board[r][c]
                    
                    if game.selected_piece:
                        if (r, c) in game.valid_moves:
                            game.execute_real_move(r, c)
                        else:
                            if clicked_piece and clicked_piece.color == 'white':
                                game.selected_piece = clicked_piece
                                game.valid_moves = game.get_valid_moves(game.selected_piece)
                            else:
                                game.selected_piece = None
                                game.valid_moves = []
                    else:
                        if clicked_piece and clicked_piece.color == 'white':
                            game.selected_piece = clicked_piece
                            game.valid_moves = game.get_valid_moves(game.selected_piece)

        game.draw()
    
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()