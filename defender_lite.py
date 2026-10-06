"""defender-lite: 极简 Defender 克隆。

玩法:驾驶飞船在横向卷轴世界里巡逻,击落 Lander(登陆者),
阻止它们抓走地面上的平民。被击落时正抓着平民的 Lander 会让平民
坠落——接住可救援(+500 分),掉到地上则死亡。智能炸弹清屏。
纯标准库,无实时输入:交互是"每行一个命令"的回合制。
"""

import argparse
import math
import random
import sys

WORLD_W = 80          # 世界宽度(格)
WORLD_H = 16          # 世界高度(格)
VIEW_W = 40           # 视口宽度(格)
GROUND = WORLD_H - 1  # 地面行

KILL_SCORE = 150      # 击落 Lander 得分
RESCUE_SCORE = 500    # 救援平民得分

PLAYER_SPEED_X = 3
PLAYER_SPEED_Y = 1
BULLET_SPEED = 3
FIRE_COOLDOWN = 3
TARGET_LANDERS = 2    # 维持的 Lander 数量
LANDER_DESCEND_EVERY = 2  # Lander 每 N 帧下降 1 格
LANDER_ASCEND_EVERY = 2   # 抓人上升时每 N 帧上升 1 格


class Human:
    """平民。state: ground / carried / falling / lost / dead。"""

    def __init__(self, x):
        self.x = x
        self.y = GROUND
        self.vy = 0.0
        self.state = "ground"


class Lander:
    """登陆者:下降抓人,抓住后上升;到顶则平民丢失。"""

    def __init__(self, x, y=0):
        self.x = x
        self.y = y
        self.alive = True
        self.carrying = None  # Human 或 None


class Bullet:
    def __init__(self, x, y, dx):
        self.x = x
        self.y = y
        self.dx = dx
        self.alive = True


class Game:
    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.player_x = WORLD_W // 2
        self.player_y = WORLD_H // 2
        self.facing = 1
        self.lives = 3
        self.bombs = 3
        self.score = 0
        self.humans = [Human(x) for x in (8, 20, 32, 48, 60, 72)]
        self.landers = []
        self.bullets = []
        self.cooldown = 0
        self.tick_n = 0
        self.kills = 0
        self.rescues = 0
        self.over = False
        self.lost_reason = ""
        for _ in range(TARGET_LANDERS):
            self._spawn_lander()

    # ---- 内部 ----
    def _spawn_lander(self):
        self.landers.append(
            Lander(self.rng.randrange(WORLD_W), self.rng.randrange(0, 4)))

    def _nearest_ground_human(self, x):
        best, bd = None, None
        for h in self.humans:
            if h.state != "ground":
                continue
            d = abs(h.x - x)
            if bd is None or d < bd:
                best, bd = h, d
        return best

    def alive_humans(self):
        return sum(1 for h in self.humans if h.state in ("ground", "carried", "falling"))

    def alive_landers(self):
        return [L for L in self.landers if L.alive]

    def _kill_lander(self, L):
        L.alive = False
        self.kills += 1
        self.score += KILL_SCORE
        if L.carrying is not None:
            h = L.carrying
            h.state = "falling"
            h.x, h.y, h.vy = L.x, L.y, 0.0
            L.carrying = None

    # ---- 主循环 ----
    def tick(self, cmd=""):
        """cmd 可含: a左 d右 w上 s下,空格开火,b智能炸弹。"""
        if self.over:
            return
        cmd = cmd.lower()

        # 玩家移动
        if "a" in cmd:
            self.player_x -= PLAYER_SPEED_X
            self.facing = -1
        if "d" in cmd:
            self.player_x += PLAYER_SPEED_X
            self.facing = 1
        if "w" in cmd:
            self.player_y -= PLAYER_SPEED_Y
        if "s" in cmd:
            self.player_y += PLAYER_SPEED_Y
        self.player_x = max(0, min(WORLD_W - 1, self.player_x))
        self.player_y = max(0, min(GROUND, self.player_y))

        # 开火
        if self.cooldown > 0:
            self.cooldown -= 1
        if " " in cmd and self.cooldown == 0:
            self.bullets.append(
                Bullet(self.player_x + self.facing * 2, self.player_y,
                       self.facing * BULLET_SPEED))
            self.cooldown = FIRE_COOLDOWN

        # 智能炸弹:清屏
        if "b" in cmd and self.bombs > 0:
            self.bombs -= 1
            for L in self.alive_landers():
                self._kill_lander(L)

        # 子弹
        for b in self.bullets:
            if not b.alive:
                continue
            b.x += b.dx
            if b.x < 0 or b.x >= WORLD_W:
                b.alive = False
                continue
            for L in self.alive_landers():
                if abs(b.x - L.x) <= 1 and abs(b.y - L.y) <= 1:
                    self._kill_lander(L)
                    b.alive = False
                    break
        self.bullets = [b for b in self.bullets if b.alive]

        # Lander
        for L in self.alive_landers():
            if L.carrying is not None:
                if self.tick_n % LANDER_ASCEND_EVERY == 0:
                    L.y -= 1
                if L.y <= 0:  # 带到顶:平民丢失
                    L.carrying.state = "lost"
                    L.carrying = None
            else:
                tgt = self._nearest_ground_human(L.x)
                if tgt is None:
                    continue
                if L.x < tgt.x:
                    L.x += 1
                elif L.x > tgt.x:
                    L.x -= 1
                if L.y < GROUND and self.tick_n % LANDER_DESCEND_EVERY == 0:
                    L.y += 1
                if L.x == tgt.x and L.y >= GROUND - 1:
                    tgt.state = "carried"
                    L.carrying = tgt

        # 坠落的平民
        for h in self.humans:
            if h.state != "falling":
                continue
            h.vy = min(h.vy + 0.5, 2.0)
            h.y += h.vy
            if abs(self.player_x - h.x) <= 1 and abs(self.player_y - h.y) <= 1:
                h.state = "ground"
                h.y = GROUND
                h.vy = 0.0
                self.rescues += 1
                self.score += RESCUE_SCORE
            elif h.y >= GROUND:
                h.state = "dead"

        # 玩家撞 Lander
        for L in self.alive_landers():
            if abs(self.player_x - L.x) <= 1 and abs(self.player_y - L.y) <= 1:
                self.lives -= 1
                self.player_x, self.player_y = WORLD_W // 2, WORLD_H // 2
                self.landers = [x for x in self.landers
                                if not x.alive or abs(x.x - self.player_x) > 10]
                if self.lives <= 0:
                    self.over = True
                    self.lost_reason = "飞船坠毁"
                break

        # 补 Lander
        if self.tick_n > 0 and self.tick_n % 30 == 0 and len(self.alive_landers()) < TARGET_LANDERS \
                and self.alive_humans() > 0:
            self._spawn_lander()

        if self.alive_humans() == 0:
            self.over = True
            self.lost_reason = "平民全部丢失"

        self.tick_n += 1

    # ---- 渲染 ----
    def render(self):
        left = max(0, min(WORLD_W - VIEW_W, self.player_x - VIEW_W // 2))
        grid = [[" "] * VIEW_W for _ in range(WORLD_H)]
        for i in range(VIEW_W):
            grid[GROUND][i] = "="
        for h in self.humans:
            vx = h.x - left
            if 0 <= vx < VIEW_W:
                if h.state == "ground":
                    grid[GROUND][vx] = "H"
                elif h.state == "falling" and 0 <= int(h.y) < WORLD_H:
                    grid[int(h.y)][vx] = "h"
        for L in self.alive_landers():
            vx, vy = L.x - left, int(L.y)
            if 0 <= vx < VIEW_W and 0 <= vy < WORLD_H:
                grid[vy][vx] = "U" if L.carrying else "L"
        for b in self.bullets:
            vx = b.x - left
            if 0 <= vx < VIEW_W and 0 <= b.y < WORLD_H:
                grid[b.y][vx] = "*"
        vx = self.player_x - left
        if 0 <= vx < VIEW_W:
            grid[self.player_y][vx] = ">" if self.facing == 1 else "<"
        return "\n".join("".join(row) for row in grid)

    def status(self):
        return (f"得分 {self.score}  生命 {self.lives}  炸弹 {self.bombs}  "
                f"平民 {self.alive_humans()}/6  击杀 {self.kills}  救援 {self.rescues}")


def auto_step(g):
    """简单 AI:先救坠落平民,否则与最近的 Lander 保持距离并开火。"""
    cmd = ""
    falling = [h for h in g.humans if h.state == "falling"]
    if falling:
        t = min(falling, key=lambda h: abs(h.x - g.player_x))
        dx, dy = t.x, min(int(t.y) + 1, GROUND)
    else:
        ls = g.alive_landers()
        if not ls:
            return ""
        # 最紧急的目标:快抓到人的( y 大)或快把人带到顶的(y 小且抓着人)
        def urgency(L):
            if L.carrying is not None:
                return 100 + (WORLD_H - int(L.y))
            return int(L.y)
        L = max(ls, key=lambda z: (urgency(z), -abs(z.x - g.player_x)))
        # 炸弹:敌人太多
        if g.bombs > 0 and len(ls) >= 4:
            return "b"
        dist_x = abs(L.x - g.player_x)
        dist_y = abs(int(L.y) - g.player_y)
        # 太近:双向拉开(玩家横向速度 3,提前量要大)
        if dist_x <= 6 and dist_y <= 3:
            cmd += "a" if g.player_x < L.x else "d"
            cmd += "w" if g.player_y < int(L.y) else "s"
            return cmd
        # 保持 4 格距离,在同行时开火
        stand = 4
        if dist_x > stand:
            cmd += "d" if g.player_x < L.x else "a"
        if g.player_y < int(L.y):
            cmd += "s"
        elif g.player_y > int(L.y):
            cmd += "w"
        if g.player_y == int(L.y) and g.cooldown == 0 \
                and (L.x - g.player_x) * g.facing > 0 and dist_x <= 25:
            cmd += " "
        return cmd
    if g.player_x < dx:
        cmd += "d"
    elif g.player_x > dx:
        cmd += "a"
    if g.player_y < dy:
        cmd += "s"
    elif g.player_y > dy:
        cmd += "w"
    return cmd


def auto_play(seed=None, frames=600, verbose=False):
    g = Game(seed)
    for _ in range(frames):
        if g.over:
            break
        g.tick(auto_step(g))
        if verbose and g.tick_n % 100 == 0:
            print(g.status())
    return g


def play_interactive(seed=None):
    g = Game(seed)
    print("defender-lite: a左 d右 w上 s下,空格开火,b炸弹,q退出(每行一命令)")
    while not g.over:
        print(g.render())
        print(g.status())
        try:
            line = input("> ")
        except EOFError:
            break
        if line.strip().lower() == "q":
            break
        g.tick(line)
    print(g.render())
    print(g.status())
    print("游戏结束:", g.lost_reason or "主动退出")


def main(argv=None):
    ap = argparse.ArgumentParser(description="defender-lite: 极简 Defender 克隆")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--auto", action="store_true", help="无头自动演示")
    ap.add_argument("--frames", type=int, default=600)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)
    if args.auto:
        g = auto_play(args.seed, args.frames, args.verbose)
        print(f"自动演示结束:得分 {g.score},击杀 {g.kills},救援 {g.rescues},"
              f"剩余平民 {g.alive_humans()}/6,生命 {g.lives},"
              f"帧数 {g.tick_n}{' ,'+g.lost_reason if g.over else ',存活'}")
    else:
        if not sys.stdin.isatty():
            print("交互模式需要终端,请用 --auto", file=sys.stderr)
            return 2
        play_interactive(args.seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
