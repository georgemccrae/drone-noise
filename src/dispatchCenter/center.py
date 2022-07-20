from commons.decorators import auto_str
from commons.enum import DroneStatus
from commons.my_util import nearest_free_drone, difference
from commons.util import Queue
from commons.configuration import CENTER_PER_SLICE_TIME, PLOT_SIMULATION, USE_NOISE_TRACKER, USE_DENSITY_MATRIX, USE_LOCAL_ORDER
from cityMap.citymap import Coordinate, CityMap
from drones.dronegenerator import DroneGenerator
from orders.ordergenerator import OrderGenerator
from dispatchCenter.plotter import Plotter
from dispatchCenter.planner import PathPlanner
from noise.tracker import NoiseTracker
from noise.matrix import DensityMatrix
import time


@auto_str
class Center:
    def __init__(self, warehouses, city_map: CityMap, num_orders, num_drones):
        self.warehouses = [Coordinate(latitude=x[0], longitude=x[1]) for x in warehouses]
        self.order_generator = OrderGenerator(city_map=city_map)
        self.drone_generator = DroneGenerator(warehouses=self.warehouses)
        self.iteration_count = 0
        self.waiting_orders = Queue()
        self.free_drones = list()
        self.delivering_drones = list()
        self.waiting_planning_drones = list()
        self.init_drones(num_drones)
        self.init_orders(num_orders)
        self.matrix = DensityMatrix()
        self.planner = PathPlanner(self.matrix)
        if USE_NOISE_TRACKER:
            self.noise_tracker = NoiseTracker()
        if PLOT_SIMULATION:
            self.plotter = Plotter(warehouses=self.warehouses, city_map=city_map)
    
    def process_orders(self):
        """
        Process all waiting orders

        If there are waiting orders and free drones, allocate these orders to the free drones.
        """
        while self.has_waiting_order() and self.has_free_drone():
            order = self.waiting_orders.pop()  # pop the least recent order
            drone = nearest_free_drone(order, self.free_drones)  # find the nearest free drone
            drone.accept_order(order)  # let the drone accept the order
            self.free_drones.remove(drone)  # remove the drone from the list of free drones
            self.waiting_planning_drones.append(drone)
    
    def plan_drones_path(self):
        """
        Plan path for drones using 'PathPlanner'
        """
        for drone in self.waiting_planning_drones:
            path = self.planner.plan(start=drone.location,
                                     end=drone.destination,
                                     time_count=self.iteration_count)
            drone.receive_path(path)
            # After receiving a path, a free drone can start to deliver food
            if drone not in self.delivering_drones:
                self.delivering_drones.append(drone)
        # Update the list of waiting for planning drones
        self.waiting_planning_drones = difference(self.waiting_planning_drones, self.delivering_drones)
    
    def update_drones(self):
        """
        Update delivering (working) drones' status and position.

        Record the current position of each working drone.
        Update drones and orders' status and positions.
        If any delivering drone completes its order, update its status and move it to the list of free drones.
        """
        for drone in self.delivering_drones:
            drone.update()
            if USE_NOISE_TRACKER:
                self.noise_tracker.track_noise(drone)
            if drone.status is DroneStatus.WAITING:
                self.free_drones.append(drone)
        self.delivering_drones = [x for x in self.delivering_drones if x not in self.free_drones]
        if USE_NOISE_TRACKER:
            self.noise_tracker.update_time_count()
        self.waiting_planning_drones.extend([x for x in self.delivering_drones if x.need_planning is True])
    
    def run(self):
        """
        Start running the center
        """
        print("Simulation starts: running the center...")
        origin_time = time.time()
        while True:
            next_iteration_time = origin_time + self.iteration_count * CENTER_PER_SLICE_TIME
            if time.time() > next_iteration_time:
                self.iteration_count += 1
                if self.has_waiting_order() or self.has_working_drone():
                    self.process_orders()
                    self.plan_drones_path()
                    self.update_drones()
                    if USE_DENSITY_MATRIX:
                        self.matrix.track_noise(self.delivering_drones)
                    if PLOT_SIMULATION:
                        self.plotter.store_plot(self.delivering_drones)
                if self.has_waiting_order() is False and \
                        self.has_working_drone() is False and \
                        self.has_planning_drone() is False:
                    print("All orders have been completed, no more new orders")
                    if USE_DENSITY_MATRIX:
                        print("Plotting noise density matrix...")
                        self.matrix.plot_matrix(time_count=self.iteration_count)
                        print("Noise density matrix has been saved to local")
                    print("Simulation ends: ending running the center...")
                    break
    
    def init_drones(self, num):
        """
        Create a number of drones and add them to the list of free drones
        """
        print("Start creating drones...")
        self.free_drones.extend(self.drone_generator.get_drones(num))
    
    def init_orders(self, num):
        """
        Create a number of orders and add them to the queue of waiting orders
        """
        print("Start initializing orders...")
        if USE_LOCAL_ORDER:
            orders = self.order_generator.load_orders()
        else:
            orders = self.order_generator.get_orders(num=num, bias=True)
        for order in orders:
            self.waiting_orders.push(order)
    
    def has_free_drone(self) -> bool:
        """Check if there is any free (recharging) drone"""
        return len(self.free_drones) > 0
    
    def has_working_drone(self) -> bool:
        """Check if there is any flying (working) drone"""
        return len(self.delivering_drones) > 0
    
    def has_waiting_order(self) -> bool:
        """Check if there is any new waiting order"""
        return self.waiting_orders.isEmpty() is False
    
    def has_planning_drone(self) -> bool:
        """Check if there is any drone waiting for planning a path"""
        return len(self.waiting_planning_drones) > 0
