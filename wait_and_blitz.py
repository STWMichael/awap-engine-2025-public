import random
from src.player import Player
from src.map import Map
from src.robot_controller import RobotController
from src.game_constants import Team, Tile, GameConstants, Direction, BuildingType, UnitType
from src.game_state import GameState

from src.units import Unit
from src.buildings import Building

class BotPlayer(Player):
    def __init__(self, map: Map):
        self.map = map

    def play_turn(self, rc: RobotController):
        team = rc.get_ally_team()
        enemy = rc.get_enemy_team()
        balance = rc.get_balance(team)  # Use balance instead of coin

        # Locate our Main Castle (for spawning and positioning)
        main_castle = None
        main_castle_id = None
        for building in rc.get_buildings(team):
            if building.type == BuildingType.MAIN_CASTLE:
                _, main_castle_id = rc.get_id_from_building(building)
                main_castle = building
                break
        if main_castle_id is None:
            return

        # Helper: Check if a given tile (x, y) is occupied by any building (allied or enemy)
        def is_tile_occupied(x, y):
            for b in rc.get_buildings(team):
                if b.x == x and b.y == y:
                    return True
            for b in rc.get_buildings(enemy):
                if b.x == x and b.y == y:
                    return True
            return False

        # -------------------------------
        # Phase 1: Defensive Stage (balance < 35)
        # -------------------------------
        # Process every catapult in control_set.
        def is_tile_occupied(x, y):
            for b in rc.get_buildings(team):
                if b.x == x and b.y == y:
                    return True
            for b in rc.get_buildings(enemy):
                if b.x == x and b.y == y:
                    return True
            return False

        # --- Common Spawn Phase ---
        # For early game, we might want to ensure we have enough catapults.
        catapult_count = 0
        for uid in rc.get_unit_ids(team):
            unit = rc.get_unit_from_id(uid)
            if unit and unit.type == UnitType.CATAPULT:
                catapult_count += 1
        if catapult_count < 20 and rc.can_spawn_unit(UnitType.CATAPULT, main_castle.id):
            rc.spawn_unit(UnitType.CATAPULT, main_castle.id)

        cat_ids = [uid for uid in rc.get_unit_ids(team) if rc.get_unit_from_id(uid) and rc.get_unit_from_id(uid).type == UnitType.CATAPULT]
        # Define parameters.
        optimal_range = 4          # For threat engagement, catapult's desired range.
        danger_threshold = 3
        protection_range = 6       # For protecting the center.
        max_center_distance = protection_range  # We want catapults to remain within this from the center.
        min_cat_separation = 3

        for cid in cat_ids:
            cat = rc.get_unit_from_id(cid)
            if not cat:
                continue
            # 1. If standing on a building, move off.
            if is_tile_occupied(cat.x, cat.y):
                dirs = rc.unit_possible_move_directions(cid)
                for d in dirs:
                    nx, ny = rc.new_location(cat.x, cat.y, d)
                    if not is_tile_occupied(nx, ny) and rc.can_move_unit_in_direction(cid, d):
                        rc.move_unit_in_direction(cid, d)
                        break
                continue
            # 2. Keep catapult within min distance from center.
            dist = rc.get_chebyshev_distance(cat.x, cat.y, main_castle.x, main_castle.y)
            if dist > max_center_distance:
                dirs = rc.unit_possible_move_directions(cid)
                dirs.sort(key=lambda d: rc.get_chebyshev_distance(*rc.new_location(cat.x, cat.y, d), main_castle.x, main_castle.y))
                best = dirs[0] if dirs else None
                if best and rc.can_move_unit_in_direction(cid, best):
                    rc.move_unit_in_direction(cid, best)
            # 3. Distribute catapults among themselves.
            for other in cat_ids:
                if other == cid:
                    continue
                other_unit = rc.get_unit_from_id(other)
                if not other_unit:
                    continue
                d_between = rc.get_chebyshev_distance(cat.x, cat.y, other_unit.x, other_unit.y)
                if d_between < min_cat_separation:
                    dirs = rc.unit_possible_move_directions(cid)
                    best = None
                    best_val = -float('inf')
                    for d in dirs:
                        nx, ny = rc.new_location(cat.x, cat.y, d)
                        if is_tile_occupied(nx, ny):
                            continue
                        separation = rc.get_chebyshev_distance(nx, ny, other_unit.x, other_unit.y)
                        if separation > best_val and rc.can_move_unit_in_direction(cid, d):
                            best_val = separation
                            best = d
                    if best:
                        rc.move_unit_in_direction(cid, best)
                        continue
            # 4. Engage enemy threats.
            enemy_units = rc.get_units(enemy)
            if enemy_units:
                threat = min(enemy_units, key=lambda u: rc.get_chebyshev_distance(cat.x, cat.y, u.x, u.y))
                d_threat = rc.get_chebyshev_distance(cat.x, cat.y, threat.x, threat.y)
                _, threat_id = rc.get_id_from_unit(threat)
                if danger_threshold <= d_threat <= optimal_range:
                    if rc.can_unit_attack_unit(cid, threat_id):
                        rc.unit_attack_unit(cid, threat_id)
                else:
                    mode = "toward" if d_threat > optimal_range else "away"
                    dirs = rc.unit_possible_move_directions(cid)
                    best = None
                    best_score = -float('inf')
                    for d in dirs:
                        nx, ny = rc.new_location(cat.x, cat.y, d)
                        if is_tile_occupied(nx, ny):
                            continue
                        nd = rc.get_chebyshev_distance(nx, ny, threat.x, threat.y)
                        score = -abs(nd - optimal_range) if mode == "toward" else nd
                        if score > best_score and rc.can_move_unit_in_direction(cid, d):
                            best_score = score
                            best = d
                    if best:
                        rc.move_unit_in_direction(cid, best)


        # -------------------------------
        # Phase 2: Expansion Stage (balance >= 35)
        # -------------------------------
        # PRIORITY: BUILD FARM FIRST!
        # Locate the enemy castle.

        # Helper to check if coordinates (x, y) are within map bounds.
        def is_in_bounds(x, y):
            return 0 <= x < self.map.width and 0 <= y < self.map.height
        
        enemy_castle = None
        for building in rc.get_buildings(enemy):
            if building.type == BuildingType.MAIN_CASTLE:
                enemy_castle = building
                break

        if enemy_castle:
            ex, ey = enemy_castle.x, enemy_castle.y
            # Define a safe zone: a 5x5 area centered on the enemy castle.
            safe_zone = set()
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    safe_zone.add((ex + dx, ey + dy))
            
            # Check for enemy threats near the enemy castle.
            # We'll consider any enemy unit (except healers) as a threat.
            enemy_threat_nearby = False
            threat_safe_range = 10  # If any enemy non-healer unit is within 5 tiles, consider it nearby.
            healer_types = {UnitType.LAND_HEALER_1, UnitType.LAND_HEALER_2, UnitType.LAND_HEALER_3}
            for enemy_unit in rc.get_units(enemy):
                # Skip healers.
                if enemy_unit.type in healer_types:
                    continue
                if rc.get_chebyshev_distance(enemy_unit.x, enemy_unit.y, ex, ey) <= threat_safe_range:
                    enemy_threat_nearynby = True
                    break

            # Set the starting search radius based on enemy threat detection.
            start_radius = 10 if enemy_threat_nearby else 6
            max_search_radius = 20  # Maximum radius to search.
            build_location = None
            found = False
            # Spiral search outward from the enemy castle.
            for r in range(start_radius, max_search_radius + 1):
                for dx in range(-r, r + 1):
                    for dy in range(-r, r + 1):
                        if max(abs(dx), abs(dy)) != r:
                            continue  # Only consider positions on the perimeter.
                        candidate_x = ex + dx
                        candidate_y = ey + dy
                        if not is_in_bounds(candidate_x, candidate_y):
                            continue
                        if (candidate_x, candidate_y) in safe_zone:
                            continue
                        if is_tile_occupied(candidate_x, candidate_y):
                            continue
                        build_location = (candidate_x, candidate_y)
                        found = True
                        break
                    if found:
                        break
                if found:
                    break

            if build_location and rc.can_build_building(BuildingType.FARM_1, build_location[0], build_location[1]):
                rc.build_building(BuildingType.FARM_1, build_location[0], build_location[1])

        # Count the number of allied farms.
        farm_count = sum(1 for building in rc.get_buildings(team) if building.type == BuildingType.FARM_1)

        # Only if we have at least 5 farms and our balance is above the cost needed for a new farm, proceed to spawn SWORDSMAN.
        if farm_count >= 5 and rc.get_balance(team) > 35:
            # For every FARM_1, attempt to spawn one SWORDSMAN (one spawn per building per round).
            for building in rc.get_buildings(team):
                if building.type == BuildingType.FARM_1:
                    _, farm_id = rc.get_id_from_building(building)
                    if farm_id is None:
                        continue
                    if rc.can_spawn_unit(UnitType.SWORDSMAN, farm_id):
                        rc.spawn_unit(UnitType.SWORDSMAN, farm_id)

            # Now, order all allied SWORDSMAN to act.
            # They will attack enemy units (if in range, Chebyshev distance ≤ 1) or the enemy castle,
            # otherwise, they move toward the enemy castle.
            swordsman_ids = []
            for unit_id in rc.get_unit_ids(team):
                unit = rc.get_unit_from_id(unit_id)
                if unit and unit.type == UnitType.SWORDSMAN:
                    swordsman_ids.append(unit_id)

            if enemy_castle:
                target_x, target_y = enemy_castle.x, enemy_castle.y
                _, castle_id = rc.get_id_from_building(enemy_castle)
                for s_id in swordsman_ids:
                    swordsman = rc.get_unit_from_id(s_id)
                    if not swordsman:
                        continue

                    # First, check for enemy units in attack range (Chebyshev distance ≤ 1).
                    enemy_units = rc.get_units(enemy)
                    attacked = False
                    for enemy_unit in enemy_units:
                        if rc.get_chebyshev_distance(swordsman.x, swordsman.y, enemy_unit.x, enemy_unit.y) <= 1:
                            _, enemy_id = rc.get_id_from_unit(enemy_unit)
                            if enemy_id is not None and rc.can_unit_attack_unit(s_id, enemy_id):
                                rc.unit_attack_unit(s_id, enemy_id)
                                attacked = True
                                break
                    if attacked:
                        continue

                    # If the enemy castle is in range, attack it.
                    if rc.get_chebyshev_distance(swordsman.x, swordsman.y, target_x, target_y) <= 1:
                        if castle_id is not None and rc.can_unit_attack_building(s_id, castle_id):
                            rc.unit_attack_building(s_id, castle_id)
                        continue

                    # Otherwise, move toward the enemy castle.
                    poss_dirs = rc.unit_possible_move_directions(s_id)
                    poss_dirs.sort(key=lambda d: rc.get_chebyshev_distance(*rc.new_location(swordsman.x, swordsman.y, d),
                                                                            target_x, target_y))
                    best_dir = poss_dirs[0] if poss_dirs else None
                    if best_dir and rc.can_move_unit_in_direction(s_id, best_dir):
                        rc.move_unit_in_direction(s_id, best_dir)
