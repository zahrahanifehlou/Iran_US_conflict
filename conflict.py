import random
import numpy as np
from collections import deque
import numpy as np


# ----------------------- Environment -----------------------
class Environment:
    def __init__(self):
        self.reset()

    def reset(self):
        self.state = {
            "tension": 0.70,
            "economy": 0.35,
            "legitimacy": 0.40,
            "military_power": 0.65,
            "international_support": 0.30,
            "public_unrest": 0.65,
            "system_collapse": False,
            "elite_cohesion": 0.50,
            "security_loyalty": 0.50,
            "collapse_risk": 0.0 ,
            "post_war_collapse": 0.0 ,
            "next_state_vec": 0.0
        }
        self.hard_power = 0.62
        self.mod_power = 0.38
        self.instability_duration = 0
        self.external_pressure = 0.75
        self.cumulative_strikes = 0
        self.war_duration = 0
        self.high_tension_duration = 0
        self.war_phase = "none"
        return self.get_state_vector()

    def get_state_vector(self):
        """Return numerical state vector (excluding boolean flag)"""
        s = self.state.copy()
        s.pop("system_collapse", None)
        return np.array(list(s.values()), dtype=np.float32)

    def update_power_balance(self):

        # In real Iran: The higher and longer the external threat, the stronger the hardline/security apparatus becomes — even if the state overall becomes weaker.
            t = self.state["tension"]
            duration = self.instability_duration


            if 0.55 < t < 0.75:
                boost = 0.07 * (t - 0.5)
                self.hard_power *= (1 + boost)


            elif t >= 0.75:
                boost = 0.06 * (t - 0.7)

                if duration > 5:
                    boost += 0.015 * (duration - 5)

                self.hard_power *= (1 + boost)

                # cohesion increases under external threat
                self.state["elite_cohesion"] *= 1.02


            if self.state["economy"] > 0.55 and self.state["legitimacy"] > 0.55:
                self.mod_power *= 1.02

            total = self.hard_power + self.mod_power
            self.hard_power = np.clip(self.hard_power / total, 0.10, 0.92)
            self.mod_power = 1.0 - self.hard_power

    def update_collapse_risk(self):
        # Regime behavior :
        # Sanctions + protests → ❌ no collapse
        # War with US/Israel → ❌ even less likely collapse short-term
        # Long crisis + elite split → ⚠️ possible collapse
        # Severe economic + legitimacy collapse + fragmentation → ✅ realistic collapse
        # PROLONGED WAR → ⚠️⚠️ significantly increases collapse risk over time


        if self.state["system_collapse"]:
            return

        # --- 1. Derived capacities ---
        repression_capacity = (
            0.6 * self.hard_power +
            0.4 * self.state["security_loyalty"]
        )

        # unrest only matters if repression fails
        effective_unrest = self.state["public_unrest"] * (1 - repression_capacity)

        # --- 2. Stress calculation (internal pressure) ---
        stress = (
            0.45 * (1 - self.state["legitimacy"]) +
            0.30 * effective_unrest +
            0.25 * (1 - self.state["economy"])
        )

        # --- 3. External threat stabilizer (war reduces collapse risk short-term) ---
        external_threat = self.state.get("external_threat", 0.0)
        stress *= (1 - 0.25 * external_threat)

        # --- 4. Regime resilience ---
        resilience = (
            0.50 * self.hard_power +
            0.20 * self.state["elite_cohesion"] +
            0.30 * self.state["security_loyalty"]
        )

        net = stress - resilience

        # --- 5. Instability duration dynamics ---
        if net > 0:
            self.instability_duration += 1
        else:
            self.instability_duration = max(0, self.instability_duration * 0.85)

        # --- 6. Collapse risk accumulation (slow burn) ---
        self.state["collapse_risk"] += max(0, net) * 0.025
        self.state["collapse_risk"] += 0.006 * self.instability_duration
        
        # --- PROLONGED WAR EFFECT: War duration amplifies collapse risk ---
        if self.war_duration > 10:
            war_fatigue = 0.008 * (self.war_duration - 10)
            self.state["collapse_risk"] += war_fatigue
            
        if self.war_duration > 20:
            severe_war_fatigue = 0.012 * (self.war_duration - 20)
            self.state["collapse_risk"] += severe_war_fatigue

        # --- 7. Economic + legitimacy fatigue over time ---
        if self.instability_duration > 6:
            fatigue = 0.008 * (self.instability_duration - 5)

            self.state["economy"] *= (1 - fatigue)
            self.state["legitimacy"] *= (1 - fatigue * 0.7)
        
        # --- PROLONGED WAR: Accelerated economic and legitimacy erosion ---
        if self.war_duration > 15:
            war_economic_drain = 0.01 * (self.war_duration - 15)
            self.state["economy"] *= (1 - war_economic_drain)
            self.state["legitimacy"] *= (1 - war_economic_drain * 0.6)

        # --- 8. Delayed security loyalty erosion (very hard to break) ---
        if (
            self.state["economy"] < 0.25 and
            self.state["legitimacy"] < 0.30 and
            self.instability_duration > 10
        ):
            self.state["security_loyalty"] *= 0.99
        
        # --- PROLONGED WAR: Security forces become exhausted and demoralized ---
        if self.war_duration > 25 and self.state["economy"] < 0.30:
            self.state["security_loyalty"] *= 0.985

        # --- 9. Elite cohesion: mostly stable, but can degrade slowly ---
        self.state["elite_cohesion"] *= 0.995
        
        # --- PROLONGED WAR: Elite cohesion fractures under sustained pressure ---
        if self.war_duration > 20:
            elite_war_fatigue = 0.003 * (self.war_duration - 20)
            self.state["elite_cohesion"] *= (1 - elite_war_fatigue)

        # --- 10. Elite fracture (nonlinear trigger) ---
        elite_fragility = (
            (1 - self.state["elite_cohesion"]) *
            (1 - self.state["security_loyalty"])
        )

        # --- 11. Shock-based collapse (realistic mechanism) ---
        collapse_risk = self.state["collapse_risk"]
        
        # --- PROLONGED WAR: Increases shock probability ---
        war_shock_multiplier = 1.0 + (0.02 * min(self.war_duration, 30))

        if collapse_risk > 0.65 and elite_fragility > 0.5:
            shock_prob = (0.15 + 0.4 * elite_fragility) * war_shock_multiplier

            if np.random.rand() < shock_prob:
                self.state["system_collapse"] = True
                return

        # extreme crisis fallback (rare but possible)
        if collapse_risk > 0.85:
            shock_prob = (0.10 + 0.5 * (1 - self.state["elite_cohesion"])) * war_shock_multiplier

            if np.random.rand() < shock_prob:
                self.state["system_collapse"] = True
                return

        # --- 12. Clamp ---
        self.state["collapse_risk"] = np.clip(self.state["collapse_risk"], 0, 1)



# ----------------------- Reward Function -----------------------
def get_reward(state, weights):
    s = state
    reward = (
        weights.get("power", 0) * s.get("military_power", 0) +
        weights.get("economy", 0) * s.get("economy", 0) +
        weights.get("legitimacy", 0) * s.get("legitimacy", 0) +
        weights.get("influence", 0) * s.get("international_support", 0) -
        weights.get("tension", 0) * s.get("tension", 0) -
        weights.get("unrest", 0) * s.get("public_unrest", 0)
    )
    if s.get("system_collapse", False):
        reward -= 5.0
    return float(reward)

# ----------------------- Post-war collapse check -----------------------
def post_war_collapse_check(env, steps_after_war=50):
#  Post-war behavior in the revised model follows a three-phase dynamic consistent with how regimes like Iran typically respond to external conflict:
# Immediate stabilization phase:
# The regime consolidates power. Legitimacy, security loyalty, and elite cohesion increase slightly, while collapse risk temporarily declines due to a rally-around-the-flag effect and stronger control by institutions like the Islamic Revolutionary Guard Corps.
# Medium-term strain phase:
# Economic pressure begins to accumulate and legitimacy slowly erodes. However, unrest only contributes to instability if repression capacity weakens, so collapse risk rises conditionally, not automatically.
# Long-term structural risk phase:
# If economic decline and legitimacy loss become severe, and especially if elite cohesion and security loyalty begin to fracture, collapse risk increases. Actual collapse occurs only through nonlinear shocks tied to elite fragmentation, not gradual deterioration.
    collapse_occurred = False

    for step_num in range(steps_after_war):

        t = env.state["tension"]
        unrest = env.state["public_unrest"]

        # --- Phase segmentation ---
        if step_num < 15:
            phase = "stabilization"
        elif step_num < 40:
            phase = "strain"
        else:
            phase = "risk"

        # --- 1. Immediate post-war stabilization ---
        if phase == "stabilization":

            env.state["legitimacy"] *= 1.002
            env.state["security_loyalty"] *= 1.003
            env.state["elite_cohesion"] *= 1.002

            # slight drop in collapse risk
            env.state["collapse_risk"] *= 0.995

        # --- 2. Medium-term strain ---
        elif phase == "strain":

            env.state["economy"] *= 0.993
            env.state["legitimacy"] *= 0.997

            # repression capacity
            repression_capacity = (
                0.6 * env.hard_power +
                0.4 * env.state["security_loyalty"]
            )

            effective_unrest = unrest * (1 - repression_capacity)

            env.state["collapse_risk"] += 0.006 * effective_unrest

        # --- 3. Long-term structural risk ---
        else:

            env.state["economy"] *= 0.992
            env.state["legitimacy"] *= 0.995

            # delayed loyalty erosion (very hard threshold)
            if (
                env.state["economy"] < 0.25 and
                env.state["legitimacy"] < 0.30
            ):
                env.state["security_loyalty"] *= 0.995
                env.state["elite_cohesion"] *= 0.995

            # gradual risk increase
            env.state["collapse_risk"] += 0.004

        # --- 4. Elite fracture mechanism ---
        elite_fragility = (
            (1 - env.state["elite_cohesion"]) *
            (1 - env.state["security_loyalty"])
        )

        # --- 5. Shock-based collapse ---
        if env.state["collapse_risk"] > 0.65 and elite_fragility > 0.5:

            shock_prob = 0.12 + 0.4 * elite_fragility

            if np.random.rand() < shock_prob:
                env.state["system_collapse"] = True

        if env.state["collapse_risk"] > 0.85:

            shock_prob = 0.1 + 0.5 * (1 - env.state["elite_cohesion"])

            if np.random.rand() < shock_prob:
                env.state["system_collapse"] = True

        # --- Clamp ---
        env.state["collapse_risk"] = np.clip(env.state["collapse_risk"], 0, 1)

        if env.state["system_collapse"]:
            collapse_occurred = True
            break

    return collapse_occurred
# ----------------------- Q-Network -----------------------
class QNetwork:
    def __init__(self, state_dim, action_dim, lr=0.01):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.lr = lr
        self.W = np.random.randn(state_dim, action_dim) * 0.1
        self.b = np.zeros(action_dim)

    def predict(self, state):
        state = np.asarray(state, dtype=np.float32).reshape(1, -1)
        return state @ self.W + self.b

    def update(self, state, action_idx, target):
        state = np.asarray(state, dtype=np.float32).reshape(1, -1)
        q_values = self.predict(state)[0]
        error = target - q_values[action_idx]

        self.W[:, action_idx] += self.lr * error * state[0]
        self.b[action_idx] += self.lr * error


# ----------------------- RL Agent -----------------------
class RLAgent:
    def __init__(self, name, weights, actions, state_dim):
        self.name = name
        self.weights = weights
        self.actions = actions
        self.action_map = {i: a for i, a in enumerate(actions)}

        self.qnet = QNetwork(state_dim, len(actions), lr=0.05)
        self.memory = deque(maxlen=3000)
        self.epsilon = 1.0
        self.epsilon_min = 0.05
        self.epsilon_decay = 0.995
        self.gamma = 0.95

    def choose_action(self, state_vec):
        if np.random.rand() < self.epsilon:
            return random.choice(self.actions)

        q_values = self.qnet.predict(state_vec)[0]
        action_idx = int(np.argmax(q_values))
        return self.action_map[action_idx]

    def remember(self, state, action, reward, next_state, done):
        action_idx = list(self.action_map.values()).index(action)
        self.memory.append((state.copy(), action_idx, reward, next_state.copy(), done))

    def replay(self, batch_size=64):
        if len(self.memory) < batch_size:
            return

        batch = random.sample(self.memory, batch_size)

        for state, action_idx, reward, next_state, done in batch:
            target = reward
            if not done:
                target += self.gamma * np.max(self.qnet.predict(next_state)[0])

            self.qnet.update(state, action_idx, target)

        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay


# ----------------------- Apply Action -----------------------
def apply_action(state, actor, action , env=None):
    # The model simulates a regime that becomes stronger under initial external pressure, but gradually accumulates
    # internal strain under prolonged conflict, with instability emerging only if elite unity and security loyalty begin to break down.

    new_state = state.copy()
    noise = lambda s=0.02: random.uniform(-s, s)

    def change_percent(key, pct):
        if key in new_state:
            new_state[key] *= (1 + pct + noise())

    if actor == "Hardliner":
        if action == "escalate":
            # Realistic: Big tension spike, short-term legitimacy boost (nationalism),
            # military power slightly hurt by counter-strikes, unrest reduced by repression + rally effect
            change_percent("tension", 0.45)                    # Strong escalation
            change_percent("legitimacy", 0.08)                 # Rally around the flag
            change_percent("military_power", -0.06)            # Damage from Israeli/US strikes
            change_percent("public_unrest", -0.09)             # Repression + nationalist unity
            change_percent("international_support", -0.12)     # Further isolation
            change_percent("elite_cohesion", 0.05)             # Hardliners consolidate
            change_percent("security_loyalty", 0.04)

        elif action == "block_negotiation":
            change_percent("international_support", -0.14)
            change_percent("tension", 0.22)
            change_percent("economy", -0.05)                   # Blocks any relief

    elif actor == "Moderate":
        if action == "negotiate":
            # Realistic: Limited effect because hardliners dominate
            change_percent("tension", -0.18)
            change_percent("international_support", 0.07)
            change_percent("economy", 0.035)
            change_percent("security_loyalty", -0.06)          # Military/IRGC unhappy with talks
            change_percent("elite_cohesion", -0.04)            # Hardliners resist

        elif action == "reform":
            # Reforms are very difficult during war
            change_percent("legitimacy", 0.06)
            change_percent("economy", 0.05)
            change_percent("public_unrest", -0.05)
            change_percent("military_power", -0.08)            # Big backlash from IRGC
            change_percent("elite_cohesion", -0.07)            # Strong elite resistance

    elif actor == "USA":
        if action == "strike":
            change_percent("tension", 0.60)
            damage = 0.10 + 0.02 * min(env.cumulative_strikes, 5)
            change_percent("military_power", -damage)

            change_percent("economy", -0.10)

            if env.cumulative_strikes < 2:
                change_percent("legitimacy", 0.04)
                change_percent("public_unrest", -0.02)
                change_percent("elite_cohesion", 0.03)
            else:
                change_percent("legitimacy", -0.08)
                change_percent("public_unrest", 0.10)
                change_percent("elite_cohesion", -0.06)

                if env.cumulative_strikes > 4 and state["economy"] < 0.3:
                    change_percent("security_loyalty", -0.05)

        elif action == "negotiate":
            # Realistic: Tension drops, but limited gains while fighting continues
            change_percent("tension", -0.28)
            change_percent("international_support", 0.08)
            change_percent("economy", 0.055)


    # Final clipping
    for k in new_state:
        if k != "system_collapse":
            new_state[k] = np.clip(new_state[k], 0.05, 0.97)

    return new_state


# ----------------------- Step -----------------------


def step(env, agents):
#In short, the system behaves like this:
# It is a dynamic balance between internal and external actors; as tension rises, it naturally shifts toward stronger hardliners and weaker moderates.
# Aggressive actions (like strikes) can create short-term unity and legitimacy, but over time they lead to erosion of military capacity, rising public unrest, and weakening elite cohesion.
# The effects of crises are nonlinear and cumulative, meaning the longer they continue, the harder the system becomes to control and the more extreme the reactions get.
# Collapse occurs when multiple stress factors converge: low security loyalty, fragmented elites, and high public unrest.
# Overall, the model suggests that systems rarely collapse suddenly; instead, they gradually weaken under accumulated pressure until they reach a tipping point and lose stability.
# PROLONGED WAR: Extended conflict duration dramatically increases collapse probability through resource depletion, elite fragmentation, and security force exhaustion.

    if env.state.get("system_collapse", False):
        return {a.name: "NONE" for a in agents}
    
    # Track war duration based on tension levels
    if env.state["tension"] > 0.65:
        env.high_tension_duration += 1
        if env.high_tension_duration > 5:
            env.war_duration += 1
            if env.war_duration <= 10:
                env.war_phase = "early"
            elif env.war_duration <= 25:
                env.war_phase = "prolonged"
            else:
                env.war_phase = "extended"
    else:
        env.high_tension_duration = 0
        if env.war_duration > 0:
            env.war_duration = max(0, env.war_duration - 0.5)

    current_state_vec = env.get_state_vector()
    chosen = {}
    next_temp_states = {}


    for agent in agents:
        action = agent.choose_action(current_state_vec)
        chosen[agent.name] = action

        temp_state = apply_action(env.state, agent.name, action, env)


        for k in temp_state:
            if k != "system_collapse":
                noise = np.random.normal(0, 0.01)
                temp_state[k] = np.clip(temp_state[k] + noise, 0, 1)

        next_temp_states[agent.name] = temp_state


    def get_weight(agent_name):
        base = 0.5

        if agent_name == "Hardliner":
            return np.clip(env.hard_power * (1 + env.state["tension"]), 0.1, 0.9)

        elif agent_name == "Moderate":
            return np.clip(env.mod_power * (1 - env.state["tension"]), 0.1, 0.9)

        else:  # مثلا USA
            return np.clip(0.6 + 0.3 * env.state["tension"], 0.2, 0.95)


    new_state = {}

    for k in env.state:
        if k == "system_collapse":
            continue

        total = 0
        weight_sum = 0

        for agent in agents:
            w = get_weight(agent.name)
            total += w * next_temp_states[agent.name][k]
            weight_sum += w

        new_state[k] = total / weight_sum

    env.state.update(new_state)


    if chosen.get("USA") == "strike":
        env.cumulative_strikes += 1


        damage_factor = 1 / (1 + np.exp(-0.5 * (env.cumulative_strikes - 5)))

        env.state["military_power"] *= (1 - 0.25 * damage_factor)

    tension = env.state["tension"]
    strikes = env.cumulative_strikes


    rally = np.exp(-0.3 * strikes)

    env.state["legitimacy"] *= (1 + 0.05 * rally - 0.08 * tension)
    env.state["public_unrest"] *= (1 + 0.1 * tension + 0.05 * strikes)


    decay = 0.02 * strikes

    env.state["elite_cohesion"] *= (1 - decay)
    env.state["security_loyalty"] *= (1 - decay * 0.8)


    if (
        env.state["elite_cohesion"] < 0.25 and
        env.state["security_loyalty"] < 0.3 and
        env.state["public_unrest"] > 0.7
    ):
        env.state["system_collapse"] = True

    env.update_power_balance()
    env.update_collapse_risk()

    return chosen


# ----------------------- Classification (keep your original) -----------------------
def classify_state(state):
    if state.get("system_collapse", False):
        return "COLLAPSE"

    tension = state["tension"]
    unrest = state["public_unrest"]
    support = state["international_support"]
    military = state["military_power"]
    economy = state["economy"]


    if tension > 0.7 and military > 0.4 and unrest > 0.3:
        return "ENDLESS WAR"


    elif tension > 0.55 and unrest > 0.2:
        return "ESCALATION"


    elif tension < 0.45 and unrest < 0.2:
        return "DE_ESCALATION"


    elif 0.45 <= tension <= 0.7 and military > 0.3 and unrest < 0.25:
        return "DETERRENCE"

    elif tension < 0.5 and support > 0.5 and economy > 0.4:
        return "DEAL"

    else:
        return "STALEMATE"


# ----------------------- Training -----------------------
import numpy as np

def train_agents(n_episodes=1000, max_steps=30):

# The system no longer moves in a single direction; it dynamically shifts between escalation, stabilization, and de-escalation depending on internal balance and external pressure.
# Hardliners tend to push toward tension and controlled confrontation, but not always full war—often favoring deterrence or limited responses.
# Moderates consistently act as a stabilizing force, promoting negotiation, reform, and gradual de-escalation when conditions allow.
# The external actor (USA) behaves strategically rather than aggressively by default, mixing pressure (strikes, sanctions) with pauses and negotiation.
# Random shocks (protests, incidents, diplomacy) introduce unpredictability, meaning the system can suddenly shift direction rather than follow a fixed path.
# As a result, the system can settle into multiple outcomes:
# Escalation spiral
# Managed tension (deterrence equilibrium)
# Temporary de-escalation or negotiation
# Prolonged stalemate (frozen conflict)


    env = Environment()
    state_dim = len(env.get_state_vector())


    hardliner = RLAgent("Hardliner", {
        "power": 0.85,
        "economy": 0.30,
        "legitimacy": 0.15,
        "tension": 0.55,
        "unrest": -0.25,
        "influence": 0.55
    }, [
        "escalate",
        "block_negotiation",
        "deterrence",          # 🔥
        "limited_response"     # 🔥
    ], state_dim)


    moderate = RLAgent("Moderate", {
        "power": 0.25,
        "economy": 0.15,
        "legitimacy": 0.20,
        "tension": -0.25,
        "unrest": -0.20,
        "influence": 0.35
    }, [
        "negotiate",
        "reform",
        "deescalate",          # 🔥
        "confidence_building"  # 🔥
    ], state_dim)


    usa = RLAgent("USA", {
        "power": 0.85,
        "economy": 0.95,
        "legitimacy": 0.75,
        "tension": 0.65,
        "unrest": -0.05,
        "influence": 0.80
    }, [
        "strike",
        "negotiate",
        "sanctions",           # 🔥
        "strategic_pause"      # 🔥
    ], state_dim)

    agents = [hardliner, moderate, usa]

    print("Starting Reinforcement Learning Training...\n")

    for episode in range(1, n_episodes + 1):
        env.reset()


        env.state["tension"] = np.clip(np.random.normal(0.5, 0.15), 0.2, 0.8)
        env.state["international_support"] = np.clip(np.random.normal(0.5, 0.2), 0.1, 0.9)
        env.state["economy"] = np.clip(np.random.normal(0.5, 0.2), 0.1, 0.9)

        for step_idx in range(max_steps):


            if np.random.rand() < 0.1:
                shock = np.random.choice(["protest", "incident", "diplomacy"])

                if shock == "protest":
                    env.state["public_unrest"] += 0.1

                elif shock == "incident":
                    env.state["tension"] += 0.12

                elif shock == "diplomacy":
                    env.state["tension"] -= 0.1
                    env.state["international_support"] += 0.08

            step(env, agents)

            if env.state.get("system_collapse", False):
                break


        for agent in agents:
            agent.replay(batch_size=64)


        for agent in agents:
            agent.epsilon = max(0.05, agent.epsilon * 0.995)

        if episode % 100 == 0:
            print(
                f"Episode {episode:4d} | "
                f"Tension: {env.state['tension']:.2f} | "
                f"Unrest: {env.state['public_unrest']:.2f} | "
                f"Collapse risk: {env.state['collapse_risk']:.2f}"
            )

    return agents, env


# ----------------------- Evaluation -----------------------
def evaluate(agents, n_eval=300):
    env = Environment()

    results = {
        "ENDLESS WAR": 0,
        "ESCALATION": 0,
        "DE_ESCALATION": 0,
        "DETERRENCE": 0,
        "DEAL": 0,
        "STALEMATE": 0,
        "COLLAPSE": 0
    }

    post_war_collapse_count = 0
    
    # Track war duration and collapse relationship
    war_duration_at_collapse = []
    collapse_by_war_phase = {"early": 0, "prolonged": 0, "extended": 0, "no_war": 0}
    total_by_war_phase = {"early": 0, "prolonged": 0, "extended": 0, "no_war": 0}

    for _ in range(n_eval):
        env.reset()

        env.state["tension"] = np.clip(np.random.normal(0.5, 0.15), 0.2, 0.8)
        env.state["international_support"] = np.clip(np.random.normal(0.5, 0.2), 0.1, 0.9)
        env.state["economy"] = np.clip(np.random.normal(0.5, 0.2), 0.1, 0.9)

        outcome = None
        max_war_duration = 0

        for _ in range(30):


            if np.random.rand() < 0.1:
                shock = np.random.choice(["protest", "incident", "diplomacy"])
                if shock == "protest":
                    env.state["public_unrest"] += 0.1
                elif shock == "incident":
                    env.state["tension"] += 0.12
                elif shock == "diplomacy":
                    env.state["tension"] -= 0.1
                    env.state["international_support"] += 0.08

            step(env, agents)
            max_war_duration = max(max_war_duration, env.war_duration)

            if env.state.get("system_collapse", False):
                outcome = "COLLAPSE"
                war_duration_at_collapse.append(env.war_duration)
                break

        if outcome is None:
            outcome = classify_state(env.state)
        
        # Track collapse by war phase
        phase = env.war_phase if env.war_duration > 0 else "no_war"
        total_by_war_phase[phase] += 1
        if outcome == "COLLAPSE":
            collapse_by_war_phase[phase] += 1

        results[outcome] += 1


        if outcome in ["ENDLESS WAR", "ESCALATION"]:
            if post_war_collapse_check(env, steps_after_war=50):
                post_war_collapse_count += 1

    print("\n=== Evaluation Results (Realistic Multi-Path Model) ===\n")
    for k, v in results.items():
        print(f"{k:12}: {v/n_eval:.3f} ({v/n_eval*100:5.1f}%)")

    print(
        f"\nPost-war collapse: {post_war_collapse_count}/{n_eval} "
        f"({post_war_collapse_count/n_eval*100:5.1f}%)"
    )
    
    # Analyze prolonged war and collapse relationship
    print("\n=== PROLONGED WAR AND REGIME COLLAPSE ANALYSIS ===\n")
    
    if war_duration_at_collapse:
        avg_war_duration = np.mean(war_duration_at_collapse)
        print(f"Average war duration at collapse: {avg_war_duration:.1f} steps")
        print(f"Min war duration at collapse: {min(war_duration_at_collapse)}")
        print(f"Max war duration at collapse: {max(war_duration_at_collapse)}")
    
    print("\nCollapse probability by war phase:")
    for phase in ["no_war", "early", "prolonged", "extended"]:
        if total_by_war_phase[phase] > 0:
            collapse_rate = collapse_by_war_phase[phase] / total_by_war_phase[phase]
            print(f"  {phase:12}: {collapse_rate:.3f} ({collapse_rate*100:5.1f}%) - {collapse_by_war_phase[phase]}/{total_by_war_phase[phase]} scenarios")
    
    # Calculate correlation between war duration and collapse
    if war_duration_at_collapse:
        short_war_collapses = sum(1 for d in war_duration_at_collapse if d <= 10)
        prolonged_war_collapses = sum(1 for d in war_duration_at_collapse if 10 < d <= 25)
        extended_war_collapses = sum(1 for d in war_duration_at_collapse if d > 25)
        
        print("\nCollapse distribution by war duration:")
        print(f"  Short war (≤10 steps): {short_war_collapses} collapses")
        print(f"  Prolonged war (11-25 steps): {prolonged_war_collapses} collapses")
        print(f"  Extended war (>25 steps): {extended_war_collapses} collapses")
        
        if prolonged_war_collapses + extended_war_collapses > 0:
            prolonged_collapse_pct = (prolonged_war_collapses + extended_war_collapses) / len(war_duration_at_collapse) * 100
            print(f"\n**{prolonged_collapse_pct:.1f}% of collapses occurred during prolonged/extended war**")




# ----------------------- Run -----------------------
if __name__ == "__main__":
    print("Training RL Agents...")
    trained_agents, final_env = train_agents(n_episodes=1000, max_steps=50)

    evaluate(trained_agents, n_eval=300)