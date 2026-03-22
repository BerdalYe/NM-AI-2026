import requests
import numpy as np
import math
import time

# --- CONFIGURATION ---
BASE_URL = "https://api.ainm.no/astar-island"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwZGZjNzhmNy1kYjFjLTQzNDAtYmU5MS1iMDZjNjQxODFiNDkiLCJlbWFpbCI6ImFybndnMDlAZ21haWwuY29tIiwiaXNfYWRtaW4iOmZhbHNlLCJleHAiOjE3NzQ2Mzk0NjN9.eKcdesEW9I-3yhwGSGN0JgrR_ndshu8WkIO5ErU6YYg"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

# --- FINAL CHAMPION CALIBRATION (ROUND 23) ---
# Survival Cap: 0.15 matches the 'flicker' rate you saw in 5 queries.
# Decay: 11.0 covers the massive expansion seen in snapshots.
SURVIVAL_CAP = 0.15   
EXPANSION_DECAY = 11.0   
FOREST_LOCK = 0.996   
STATIC_LOCK = 0.998   

def apply_safety_floor(pred):
    """Prevents zero-probability penalties (KL Divergence protection)."""
    pred = np.maximum(pred, 0.0005) 
    sums = pred.sum(axis=-1, keepdims=True)
    return (pred / sums).tolist()

def generate_final_ghost_empire(initial_grid, height, width, settlements_0):
    # Classes: 0:Empty, 1:Settle, 2:Port, 3:Ruin, 4:Forest, 5:Mountain
    pred = np.full((height, width, 6), 0.0005)
    s_coords = [(s['y'], s['x']) for s in settlements_0 if s['alive']]

    for y in range(height):
        for x in range(width):
            cell = initial_grid[y][x]
            
            # 1. HARD ANCHOR STATIC TERRAIN (The Foundation Score)
            # This is 90% of your points. We lock them so no expansion prob leaks here.
            if cell == 5: pred[y, x] = [0.0005, 0.0005, 0.0005, 0.0005, 0.0005, STATIC_LOCK]; continue
            if cell == 10: pred[y, x] = [STATIC_LOCK, 0.0005, 0.0005, 0.0005, 0.0005, 0.0005]; continue
            if cell == 4: pred[y, x] = [0.001, 0.0005, 0.0005, 0.0005, FOREST_LOCK, 0.0005]; continue

            # 2. THE GHOST CLOUD (Gaussian Math)
            min_dist = min([abs(y-sy) + abs(x-sx) for sy, sx in s_coords]) if s_coords else 99
            
            # Create a smooth fade from hubs: p = Cap * e^(-d/k)
            influence = SURVIVAL_CAP * math.exp(-min_dist / EXPANSION_DECAY)
            
            p_settle = influence
            p_ruin = influence * 0.20 # Buffer for the red tiles you saw
            
            # 3. INTERNAL FJORD PORT LOGIC
            p_port = 0.0005
            is_coastal = any(initial_grid[y+dy][x+dx] == 10 for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)] 
                             if 0 <= y+dy < height and 0 <= x+dx < width)
            if is_coastal and p_settle > 0.02:
                p_port = p_settle * 0.12
                p_settle *= 0.88

            # 4. DOMINANT EMPTY BASELINE (Safety Strategy)
            # Probability mass not used by the ghosts becomes Empty (Class 0).
            p_empty = 1.0 - (p_settle + p_port + p_ruin + 0.01)
            
            pred[y, x] = [p_empty, p_settle, p_port, p_ruin, 0.005, 0.001]

    return apply_safety_floor(pred)

def submit_final_round():
    r_resp = requests.get(f"{BASE_URL}/rounds", headers=HEADERS).json()
    active = next((rd for rd in r_resp if rd["status"] == "active"), None)
    if not active: 
        print("❌ NO ACTIVE ROUND! Competition may be closing.")
        return
    
    details = requests.get(f"{BASE_URL}/rounds/{active['id']}", headers=HEADERS).json()
    print(f"🏆 FINAL SUBMISSION: Round {active['round_number']} | Multiplier: {active['round_weight']}")

    for i in range(5):
        print(f"📦 Processing Seed {i}...", end=" ", flush=True)
        grid = details["initial_states"][i]["grid"]
        sets = details["initial_states"][i]["settlements"]
        prediction = generate_final_ghost_empire(grid, 40, 40, sets)
        
        resp = requests.post(f"{BASE_URL}/submit", headers=HEADERS, json={
            "round_id": active["id"], "seed_index": i, "prediction": prediction
        })
        
        if resp.status_code == 200:
            print("✅ DONE")
        else:
            print(f"❌ FAILED: {resp.text}")
        time.sleep(0.5)

if __name__ == "__main__":
    submit_final_round()