from src.player import Player
from src.map import Map
from src.robot_controller import RobotController
from src.game_constants import Team, Tile, GameConstants, Direction, BuildingType, UnitType

from src.units import Unit
from src.buildings import Building

class BotPlayer(Player):
    def __init__(self, map: Map):
        self.map = map


    def play_turn(self, rc: RobotController):
        def get_neighbors(pos):
            x, y = pos
            return [(x+dx, y+dy) for dx, dy in [(-1,0),(1,0),(0,-1),(0,1),
                                                (-1,-1),(-1,1),(1,-1),(1,1)]]
        
        def auto_attack(unit_id, enemy_ids):
            for enemy_unit_id in enemy_ids:
                if rc.can_unit_attack_unit(unit_id, enemy_unit_id):
                    rc.unit_attack_unit(unit_id, target_enemy)

        def dfs_find_path_to_free(formation, start, bool_map):
            """
            Starting from 'start' (a cell in formation), perform a DFS
            over adjacent cells that are in the formation.
            Return a path (list of positions) from start to a cell that has at least one free neighbor.
            """
            stack = [(start, [start])]
            visited = set()
            while stack:
                current, path = stack.pop()
                if current in visited:
                    continue
                visited.add(current)
                # Check if current has a free neighbor (i.e. not in formation).
                for nb in get_neighbors(current):
                    m = rc.get_map()
                    if (not m.in_bounds(nb[0], nb[1])) or (not m.is_tile_type(nb[0], nb[1], Tile.GRASS)):
                        continue
                    if nb not in formation:
                        # Found a free neighbor; return the path (we don't include the free cell itself).
                        return path
                # Otherwise, continue DFS over neighbors that are in formation.
                for nb in get_neighbors(current):
                    if nb in formation and nb not in visited:
                        stack.append((nb, path + [nb]))

            # print("No path found")
            return None

        def unblock_spawn(rc, formation, spawn, bool_map):
            """
            Given a formation mapping (pos -> unit id) and a spawn cell (a tuple),
            if the spawn is occupied, perform a DFS from spawn to find a path to a free neighbor.
            Then, move the units along that path (starting with the boundary unit) so that the spawn cell becomes free.
            """
            if spawn not in formation:
                return  # spawn already free
            # print("Blocked")
            # print(bool_map)
            path = dfs_find_path_to_free(formation, spawn, bool_map)
            # print(path)
            if path is None:
                return  # no path found
            # The path is from spawn (index 0) to some boundary cell.
            # First, move the boundary unit out: that is, from the last cell in the path,
            # find one neighbor that is free.
            boundary_pos = path[-1]
            boundary_uid = formation[boundary_pos]
            unit = rc.get_unit_from_id(boundary_uid)
            moved = False
            for d in rc.unit_possible_move_directions(boundary_uid):
                new_x, new_y = rc.new_location(unit.x, unit.y, d)
                if (new_x, new_y) not in formation:
                    if rc.can_move_unit_in_direction(boundary_uid, d):
                        rc.move_unit_in_direction(boundary_uid, d)
                        moved = True
                        break
            if not moved:
                return  # could not move boundary unit; give up
            # Now, move the remaining units along the path in reverse order.
            # For example, if path is [A, B, C] (A = spawn, C = boundary), then move unit at B into A's cell, then unit at C into B's cell.
            for i in range(len(path)-1, 0, -1):
                src = path[i]
                dst = path[i-1]
                uid = formation.get(src)
                if uid is None:
                    continue
                # Determine direction from src to dst.
                dx = dst[0] - src[0]
                dy = dst[1] - src[1]
                # Map offset to Direction.
                direction = None
                if dx == 1 and dy == 0:
                    direction = Direction.RIGHT
                elif dx == -1 and dy == 0:
                    direction = Direction.LEFT
                elif dx == 0 and dy == 1:
                    direction = Direction.UP
                elif dx == 0 and dy == -1:
                    direction = Direction.DOWN
                elif dx == 1 and dy == 1:
                    direction = Direction.UP_RIGHT
                elif dx == -1 and dy == 1:
                    direction = Direction.UP_LEFT
                elif dx == 1 and dy == -1:
                    direction = Direction.DOWN_RIGHT
                elif dx == -1 and dy == -1:
                    direction = Direction.DOWN_LEFT
                if direction is not None and rc.can_move_unit_in_direction(uid, direction):
                    rc.move_unit_in_direction(uid, direction)
            # print("Unblocked spawn cell at", spawn)
        

        team = rc.get_ally_team()
        ally_castle_id = -1

        # Get our main castle id
        for building in rc.get_buildings(team):
            if building.type == BuildingType.MAIN_CASTLE:
                # Using index [1] as in your provided code.
                ally_castle_id = rc.get_id_from_building(building)[1]
                break

        # Get enemy main castle id
        enemy = rc.get_enemy_team()
        enemy_castle_id = -1
        for building in rc.get_buildings(enemy):
            if building.type == BuildingType.MAIN_CASTLE:
                enemy_castle_id = rc.get_id_from_building(building)[1]
                break

        enemy_castle = rc.get_building_from_id(enemy_castle_id)
        ally_castle = rc.get_building_from_id(ally_castle_id)
        if enemy_castle is None:
            return

        turn = rc.get_turn()
        # print(f"Turn: {turn}\n")
        # print(rc.get_unit_ids(team))

        # --- Call our unblock_spawn routine.
        # Define spawn as a single cell adjacent to the castle. For example, if our castle spawns to the right:
        spawn = (ally_castle.x, ally_castle.y)
        # Build formation mapping: positions occupied by knights.
        formation = {}
        for uid in rc.get_unit_ids(team):
            unit = rc.get_unit_from_id(uid)
            if unit is not None:
                pos = (unit.x, unit.y)
                formation[pos] = uid
        # print(formation)
        # print(spawn)
        # Unblock spawn if necessary.
        bool_map = rc.get_unit_placeable_map()
        unblock_spawn(rc, formation, spawn, bool_map)

        # Process each unit.
        for unit_id in rc.get_unit_ids(team):
            unit = rc.get_unit_from_id(unit_id)
            if unit is None:
                continue

            # For non-catapult units: attack enemy castle if possible; else, move toward enemy castle.
            dist = rc.get_chebyshev_distance(unit.x, unit.y, ally_castle.x, ally_castle.y)
            if unit.type != UnitType.CATAPULT:
                if enemy_castle_id in rc.get_building_ids(enemy) and rc.can_unit_attack_building(unit_id, enemy_castle_id):
                    rc.unit_attack_building(unit_id, enemy_castle_id)
                elif dist > 1   :
                    possible_move_dirs = rc.unit_possible_move_directions(unit_id)
                    possible_move_dirs.sort(key=lambda d: rc.get_chebyshev_distance(*rc.new_location(unit.x, unit.y, d), enemy_castle.x, enemy_castle.y))
                    best_dir = possible_move_dirs[0] if possible_move_dirs else Direction.STAY
                    if rc.can_move_unit_in_direction(unit_id, best_dir):
                        rc.move_unit_in_direction(unit_id, best_dir)
                else:
                    auto_attack(unit_id, rc.get_unit_ids(enemy))
                    # print("Attacked enemy unit")
                continue

            # For Catapult units (defensive behavior):
            castle = rc.get_building_from_id(ally_castle_id)
            if castle is None:
                continue

            # 1. If the catapult is on the castle tile, move it off.
            if unit.x == castle.x and unit.y == castle.y:
                # print("Catapult blocking spawn; moving off castle")
                possible_move_dirs = rc.unit_possible_move_directions(unit_id)
                valid_moves = []
                for d in possible_move_dirs:
                    new_x, new_y = rc.new_location(unit.x, unit.y, d)
                    if rc.get_chebyshev_distance(new_x, new_y, castle.x, castle.y) > 0:
                        valid_moves.append((d, rc.get_chebyshev_distance(new_x, new_y, castle.x, castle.y)))
                if valid_moves:
                    valid_moves.sort(key=lambda tup: tup[1])
                    best_dir = valid_moves[0][0]
                    if rc.can_move_unit_in_direction(unit_id, best_dir):
                        rc.move_unit_in_direction(unit_id, best_dir)
                        # print("Moved catapult off castle\n")
                continue  # Skip further commands for this catapult this turn.

            # 2. Check for any dangerous enemy: if an enemy unit is within 3 tiles of the catapult.
            enemy_ids = rc.get_unit_ids(enemy)
            dangerous_enemy = None
            min_enemy_distance = float('inf')
            for enemy_unit_id in enemy_ids:
                if rc.can_unit_attack_unit(unit_id, enemy_unit_id):
                    enemy_unit = rc.get_unit_from_id(enemy_unit_id)
                    if enemy_unit is None:
                        continue
                    dist_to_enemy = rc.get_chebyshev_distance(unit.x, unit.y, enemy_unit.x, enemy_unit.y)
                    if dist_to_enemy < min_enemy_distance:
                        min_enemy_distance = dist_to_enemy
                        dangerous_enemy = enemy_unit

            # Get current distance from castle.
            cur_castle_dist = rc.get_chebyshev_distance(unit.x, unit.y, castle.x, castle.y)
            ideal_min = 3
            ideal_max = 7

            # 3. If a dangerous enemy is too close (<3 tiles), try to retreat from it.
            if dangerous_enemy is not None and min_enemy_distance < 3:
                possible_move_dirs = rc.unit_possible_move_directions(unit_id)
                valid_moves = []
                for d in possible_move_dirs:
                    new_x, new_y = rc.new_location(unit.x, unit.y, d)
                    new_enemy_dist = rc.get_chebyshev_distance(new_x, new_y, dangerous_enemy.x, dangerous_enemy.y)
                    new_castle_dist = rc.get_chebyshev_distance(new_x, new_y, castle.x, castle.y)
                    # Only consider moves that preserve the ideal range if possible.
                    if ideal_min <= new_castle_dist <= ideal_max:
                        valid_moves.append((d, new_enemy_dist))
                if valid_moves:
                    # Choose move that maximizes distance from the dangerous enemy.
                    valid_moves.sort(key=lambda tup: tup[1], reverse=True)
                    best_dir = valid_moves[0][0]
                    if rc.can_move_unit_in_direction(unit_id, best_dir):
                        rc.move_unit_in_direction(unit_id, best_dir)
                        # print("Catapult retreats from enemy (danger close)\n")
                    continue
                # If no ideal move found, fallback to any move that increases enemy distance.
                else:
                    possible_move_dirs.sort(key=lambda d: rc.get_chebyshev_distance(*rc.new_location(unit.x, unit.y, d), dangerous_enemy.x, dangerous_enemy.y), reverse=True)
                    best_dir = possible_move_dirs[0] if possible_move_dirs else Direction.STAY
                    if rc.can_move_unit_in_direction(unit_id, best_dir):
                        rc.move_unit_in_direction(unit_id, best_dir)
                        # print("Catapult retreats from enemy (fallback)\n")
                    continue

            # 4. If no immediate enemy threat, adjust position to maintain an ideal range from the castle.
            #    If too close (<3), move away; if too far (>7), move closer.
            if cur_castle_dist < ideal_min or cur_castle_dist > ideal_max:
                possible_move_dirs = rc.unit_possible_move_directions(unit_id)
                valid_moves = []
                for d in possible_move_dirs:
                    new_x, new_y = rc.new_location(unit.x, unit.y, d)
                    new_castle_dist = rc.get_chebyshev_distance(new_x, new_y, castle.x, castle.y)
                    # Prioritize moves that bring us into the ideal zone.
                    if ideal_min <= new_castle_dist <= ideal_max:
                        valid_moves.append((d, abs(new_castle_dist - ((ideal_min + ideal_max) / 2))))
                if valid_moves:
                    # Choose move that minimizes deviation from the center of the ideal range.
                    valid_moves.sort(key=lambda tup: tup[1])
                    best_dir = valid_moves[0][0]
                    if rc.can_move_unit_in_direction(unit_id, best_dir):
                        rc.move_unit_in_direction(unit_id, best_dir)
                        # print("Catapult repositions to ideal range\n")
                    continue
                # If no ideal moves are available, try to adjust in the correct direction.
                else:
                    # If too close, move away from castle.
                    if cur_castle_dist < ideal_min:
                        possible_move_dirs.sort(key=lambda d: rc.get_chebyshev_distance(*rc.new_location(unit.x, unit.y, d), castle.x, castle.y), reverse=True)
                    else:  # too far, move toward castle.
                        possible_move_dirs.sort(key=lambda d: rc.get_chebyshev_distance(*rc.new_location(unit.x, unit.y, d), castle.x, castle.y))
                    best_dir = possible_move_dirs[0] if possible_move_dirs else Direction.STAY
                    if rc.can_move_unit_in_direction(unit_id, best_dir):
                        rc.move_unit_in_direction(unit_id, best_dir)
                        # print("Catapult adjusts position relative to castle\n")
                    continue

            # 5. Otherwise, if an enemy unit is in attack range, attack the one closest to the castle.
            target_enemy = None
            min_dist_to_castle = float('inf')
            for enemy_unit_id in enemy_ids:
                if rc.can_unit_attack_unit(unit_id, enemy_unit_id):
                    enemy_unit = rc.get_unit_from_id(enemy_unit_id)
                    if enemy_unit is None:
                        continue
                    dist_to_castle = rc.get_chebyshev_distance(castle.x, castle.y, enemy_unit.x, enemy_unit.y)
                    if dist_to_castle < min_dist_to_castle:
                        min_dist_to_castle = dist_to_castle
                        target_enemy = enemy_unit_id
            if target_enemy is not None:
                rc.unit_attack_unit(unit_id, target_enemy)
            else:
                if enemy_castle_id in rc.get_building_ids(enemy) and rc.can_unit_attack_building(unit_id, enemy_castle_id):
                    rc.unit_attack_building(unit_id, enemy_castle_id)
                    # print("Attacked castle")
            # Otherwise, do nothing (the catapult is already in the ideal zone).

        # Spawn logic:
        # For rounds 1-3, spawn Catapults; from round 4 onward, spawn Knights.
        if rc.can_spawn_unit(UnitType.CATAPULT, ally_castle_id):
            rc.spawn_unit(UnitType.CATAPULT, ally_castle_id)
            # print("Spawned catapult\n")
        if rc.can_spawn_unit(UnitType.KNIGHT, ally_castle_id):
            rc.spawn_unit(UnitType.KNIGHT, ally_castle_id)
