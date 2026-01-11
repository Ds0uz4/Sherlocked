import gradio as gr
import importlib.util
import time
import random
from collections import defaultdict

# Mapping for the Agent's "Eyes" (Radar)
RADAR_ENCODING = {
    "EMPTY": 0,
    "WALL": 1,
    "GOAL": 2,
    "ICE": 3,
    "MUD": 4,
    "DANGER": 5,
    "CHARGER": 6,
    "ENEMY": 7
}

class MegaWorldEnv:
    def __init__(self):
        self.start = (1, 1)
        self.goal = (18, 18)

        # 1. Generate Map
        self.walls = self._generate_walls()
        
        # 2. Hazards
        self.ice = [(5,y) for y in range(5,15)] + [(15,y) for y in range(5,15)]
        self.mud = [(x,10) for x in range(2,18)]
        
        # Traps (Randomized locations)
        self.traps = [(3,3), (8,8), (12,12), (17,17), (9,10), (11,10)]
        random.shuffle(self.traps)

        # Chargers
        self.chargers = [(18,2), (10,10)]

        # 3. ENEMIES (Simplified for Random Movement)
        # We just need their starting positions now
        self.enemies = [
            {"pos": [5, 5]},
            {"pos": [15, 5]},
            {"pos": [12, 12]},
            {"pos": [16, 16]},
            {"pos": [8, 14]} # Added one more for fun
        ]

    def _generate_walls(self):
        walls = []
        for i in range(20):
            if i % 4 == 0:
                for j in range(5, 15):
                    walls.append((i, j))
        walls += [(6,6), (7,7), (13,13), (14,14)]
        return walls

    def shaped_reward(self, old_pos, new_pos):
        """
        Guide the agent: Moving closer to goal = Positive Reward
        """
        old_d = abs(old_pos[0] - self.goal[0]) + abs(old_pos[1] - self.goal[1])
        new_d = abs(new_pos[0] - self.goal[0]) + abs(new_pos[1] - self.goal[1])
        return 3.0 * (old_d - new_d)

    def get_radar(self, pos):
        """
        Returns what is in the 4 adjacent squares
        """
        x, y = pos
        radar = {}
        dirs = {"up": (x, y+1), "down": (x, y-1), "left": (x-1, y), "right": (x+1, y)}
        
        for d, (nx, ny) in dirs.items():
            info = "EMPTY"
            if not (0 <= nx < 20 and 0 <= ny < 20): info = "WALL"
            elif (nx, ny) in self.walls: info = "WALL"
            elif (nx, ny) == self.goal: info = "GOAL"
            elif (nx, ny) in self.ice: info = "ICE"
            elif (nx, ny) in self.mud: info = "MUD"
            elif (nx, ny) in self.traps: info = "DANGER"
            elif (nx, ny) in self.chargers: info = "CHARGER"
            
            # Check if any enemy is here
            for e in self.enemies:
                if tuple(e["pos"]) == (nx, ny): 
                    info = "ENEMY"
            
            radar[d] = RADAR_ENCODING[info]
        return radar

    def update_enemies(self, player_pos):
        """
        NEW LOGIC: RANDOM WALK
        Enemies pick a random valid neighbor and move there.
        """
        for e in self.enemies:
            x, y = e["pos"]
            possible_moves = []
            
            # Check Up, Down, Left, Right
            candidates = [(x, y+1), (x, y-1), (x-1, y), (x+1, y)]
            
            for nx, ny in candidates:
                # Ensure they don't walk into walls or off the map
                if 0 <= nx < 20 and 0 <= ny < 20 and (nx, ny) not in self.walls:
                    possible_moves.append((nx, ny))
            
            # Pick a random move
            if possible_moves:
                e["pos"] = list(random.choice(possible_moves))

    def render(self, player_pos, history, battery, score):
        html = "<div style='background:#000;padding:10px;border-radius:12px; font-family: monospace;'>"
        html += f"<div style='color:white; margin-bottom: 5px;'>🔋 {battery}% | 🏆 {score:.1f}</div>"
        html += "<div style='display:grid;grid-template-columns:repeat(20,22px);gap:1px'>"
        
        enemy_pos = [tuple(e["pos"]) for e in self.enemies]
        
        for y in range(19, -1, -1):
            for x in range(20):
                pos = (x, y)
                color = "#111"; char = ""
                
                if pos in self.walls: color = "#555"
                elif pos in self.ice: color = "#29b6f6"
                elif pos in self.mud: color = "#4e342e"
                elif pos in history: color = "#263238"
                
                if pos == self.goal: char = "🏁"; color = "#4caf50"
                if pos in self.chargers: char = "⚡"; color = "#fdd835"
                if pos in enemy_pos: char = "👾"; color = "#d500f9" # Ghost icon
                
                if pos == player_pos:
                    char = "🤖"
                    color = "#2196f3" if battery > 20 else "#ff6f00"
                
                html += f"<div style='width:22px;height:22px;background:{color};display:flex;align-items:center;justify-content:center;color:white;'>{char}</div>"
        
        html += "</div></div>"
        return html

def run_mega_simulation(file):
    env = MegaWorldEnv()
    if file is None:
        yield env.render(env.start, [], 100, 0), {}
        return

    spec = importlib.util.spec_from_file_location("agent", file.name)
    agent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agent)

    pos = list(env.start)
    battery = 100
    score = 0
    history = []

    for step in range(300):
        # 1. AI Decision
        radar = env.get_radar(pos)
        try:
            action = agent.get_action(pos[:], radar, battery)
        except: break

        # 2. Movement Physics
        dx, dy = [(0, 1), (0, -1), (-1, 0), (1, 0)][action]
        prev_pos = pos[:]

        nx, ny = pos[0] + dx, pos[1] + dy
        
        # Wall/Bounds Check
        if not (0 <= nx < 20 and 0 <= ny < 20) or (nx, ny) in env.walls:
            nx, ny = pos # Hit wall, stay put
        pos = [nx, ny]

        # 3. Environment Updates
        env.update_enemies(pos) # Enemies move randomly now
        history.append(tuple(pos))

        # 4. Scoring & Battery
        battery -= 1
        if tuple(pos) in env.mud: battery -= 5

        reward = env.shaped_reward(tuple(prev_pos), tuple(pos))

        if prev_pos == pos: reward -= 5 # Penalty for standing still
        if tuple(pos) in env.traps:
            reward -= 10; battery -= 10
            
        done = False
        
        # Check Collision with Enemies
        if battery <= 0 or tuple(pos) in [tuple(e["pos"]) for e in env.enemies]:
            reward -= 20; done = True
            
        if tuple(pos) == env.goal:
            reward += 1000; done = True

        reward = max(reward, -10)
        score += reward

        # 5. RL Observation Hook (Optional)
        if hasattr(agent, "observe"):
            agent.observe(reward, pos, radar, battery, done)

        yield env.render(tuple(pos), history, battery, score), {"step": step, "reward": round(reward, 2)}

        if done: return
        time.sleep(0.05)

# --- GRADIO LAUNCH ---
with gr.Blocks() as demo:
    gr.Markdown("# 🌍 Super RL World: Random Chaos Edition")
    with gr.Row():
        game = gr.HTML(MegaWorldEnv().render((1,1), [], 100, 0))
        with gr.Column():
            file = gr.File(label="Upload agent.py")
            btn = gr.Button("🚀 Run Simulation")
            log = gr.JSON(label="Live Stats")
    
    btn.click(run_mega_simulation, file, [game, log])

demo.launch()
#hello