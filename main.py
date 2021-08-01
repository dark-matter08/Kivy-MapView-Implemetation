import random
from datetime import datetime
from math import *
import certifi
from kivy.core import image
import googlemaps
import polyline
from kivy.core.window import Window
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.garden.mapview import (MapLayer, MapMarker, MapMarkerPopup,
                                 MapSource, MapView)
from kivy.garden.mapview.mapview import (MAX_LATITUDE, MAX_LONGITUDE,
                                         MIN_LATITUDE, MIN_LONGITUDE)
from kivy.garden.mapview.mapview.utils import clamp
from kivy.graphics import Color, Line, MatrixInstruction, SmoothLine
from kivy.graphics.context_instructions import Scale, Translate
from kivy.logger import Logger
from kivy.utils import platform
from kivymd.app import MDApp
from kivymd.uix.dialog import MDDialog
from kivy.properties import StringProperty
# from kivy.properties import ColorProperty, NumericProperty, StringProperty, ObjectProperty, BooleanProperty

MAP_API_KEY = "AIzaSyCkf-jwvZ1V0EwSg_SZkJBku4-woyzeLO4"
Window.size = (365, 600)

class LineMapLayer(MapLayer):
    def __init__(self, **kwargs):
        super(LineMapLayer, self).__init__(**kwargs)
        self._coordinates = []
        self._line_points = None
        self._line_points_offset = (0, 0)
        self._ms = None
        self.zoom = 0

    @property
    def coordinates(self):
        return self._coordinates

    @coordinates.setter
    def coordinates(self, coordinates):
        self._coordinates = coordinates
        self.invalidate_line_points()
        self.clear_and_redraw()

    @property
    def line_points(self):
        if self._line_points is None:
            self.calc_line_points()
        return self._line_points

    @property
    def line_points_offset(self):
        if self._line_points is None:
            self.calc_line_points()
        return self._line_points_offset

    @property
    def ms(self):
        if self._ms is None:
            mapview = self.parent
            map_source = mapview.map_source
            self._ms = pow(2.0, mapview.zoom) * map_source.dp_tile_size
        return self._ms

    def calc_line_points(self):
        # Offset all points by the coordinates of the first point, to keep coordinates closer to zero.
        # (and therefore avoid some float precision issues when drawing lines)
        self._line_points_offset = (self.get_x(self.coordinates[0][1]), self.get_y(self.coordinates[0][0]))
        # Since lat is not a linear transform we must compute manually
        self._line_points = [(self.get_x(lon) - self._line_points_offset[0], self.get_y(lat) - self._line_points_offset[1]) for lat, lon in self.coordinates]

    def invalidate_line_points(self):
        self._line_points = None
        self._line_points_offset = (0, 0)

    def get_x(self, lon):
        '''Get the x position on the map using this map source's projection
        (0, 0) is located at the top left.
        '''
        return clamp(lon, MIN_LONGITUDE, MAX_LONGITUDE) * self.ms / 360.0

    def get_y(self, lat):
        '''Get the y position on the map using this map source's projection
        (0, 0) is located at the top left.
        '''
        lat = radians(clamp(-lat, MIN_LATITUDE, MAX_LATITUDE))
        return ((1.0 - log(tan(lat) + 1.0 / cos(lat)) / pi)) * self.ms / 2.0

    def reposition(self):
        mapview = self.parent

        # Must redraw when the zoom changes
        # as the scatter transform resets for the new tiles
        if (self.zoom != mapview.zoom):
            self._ms = None
            self.invalidate_line_points()
            self.clear_and_redraw()

    def clear_and_redraw(self, *args):
        with self.canvas:
            # Clear old line
            self.canvas.clear()

        # FIXME: Why is 0.05 a good value here? Why does 0 leave us with weird offsets?
        Clock.schedule_once(self._draw_line, 0.05)

    def _draw_line(self, *args):
        mapview = self.parent
        self.zoom = mapview.zoom

        # When zooming we must undo the current scatter transform
        # or the animation distorts it
        scatter = mapview._scatter
        sx, sy, ss = scatter.x, scatter.y, scatter.scale

        # Account for map source tile size and mapview zoom
        vx, vy, vs = mapview.viewport_pos[0], mapview.viewport_pos[1], mapview.scale

        with self.canvas:
            # Clear old line
            self.canvas.clear()

            # Offset by the MapView's position in the window
            Translate(*mapview.pos)

            # Undo the scatter animation transform
            Scale(1 / ss, 1 / ss, 1)
            Translate(-sx, -sy)

            # Apply the get window xy from transforms
            Scale(vs, vs, 1)
            Translate(-vx, -vy)

            # Apply the what we can factor out of the mapsource long, lat to x, y conversion
            Translate(self.ms / 2, 0)

            # Translate by the offset of the line points (this keeps the points closer to the origin)
            Translate(*self.line_points_offset)

            # Draw line
            Color(41/255, 162/255, 251/255, 0.25)
            Line(points=self.line_points, width=6.5 / 2)
            Color(41/255, 162/255, 251/255, 1)
            Line(points=self.line_points, width=6 / 2)
            Color(0, 0.7, 1, 1)
            Line(points=self.line_points, width=4 / 2)

class MapMarkerClass(MapMarkerPopup):
    image_src = StringProperty()
    label_one = StringProperty()
    label_two = StringProperty()
    # def on_release(self):
    #     # open up the LocationPopupMenu
    #     menu = MDDialog(title=self.marker_data, text = "Here will be some data about this location")
    #     # menu.size_hint = [.8, .8]
    #     menu.pos_hint = {'center_x': .5, 'center_y': .5}
    #     menu.open()

    #     label_title = Label(text=self.marker_data)
    #     label_data = Label(text=f"Here will be some data about this location, {self.marker_data}")
    #     image = Image(source = "dummy.png", mipmap = True)
    #     layout_sub = BoxLayout(orientation = "vertical", padding = "2dp")
    #     layout_sub.add_widget(label_title)
    #     layout_sub.add_widget(label_data)
    #     layout = BoxLayout(orientation = "horizontal", padding = "5dp")
    #     layout.add_widget(image)
    #     layout.add_widget(layout_sub)
    #     bubble = Bubble()
    #     bubble.add_widget(bubble)

class GpsBlinker(MapMarker):
    def blink(self):
        # Animation that changes the blink size and opacity
        anim = Animation(outer_opacity=0, blink_size=50)
        # when the animation completes, reset the animation, then repeat
        anim.bind(on_complete=self.reset)
        anim.start(self)

    def reset(self, *args):
        self.outer_opacity = 1
        self.blink_size = self.default_blink_size
        self.blink()

class GpsHelper():
    has_centered_map = False
    def run(self):
        # get a reference to gpsblinker, then call blink()
        gps_blinker = MDApp.get_running_app().root.ids.mapview.ids.blinker
        gps_blinker.blink()
        gps_blinker.lat = 4.1587278341067755
        gps_blinker.lon = 9.28267375685355

        # request permission on Android
        if platform == 'android':
            from android.permissions import Permission, request_permissions
            def callback(permission, results):
                if all([res for res in results]):
                    print("Got all permissions")
                    from plyer import gps
                    gps.configure(on_location=self.update_blinker_position, on_status=self.on_auth_status)
                    gps.start(minTime=1000, minDistance=0)
                else:
                    print("Did not get all permissions")
            request_permissions([Permission.ACCESS_COARSE_LOCATION, Permission.ACCESS_FINE_LOCATION], callback)

        # configure gps
        if platform == 'ios':
            from plyer import gps
            gps.configure(on_location=self.update_blinker_position, on_status=self.on_auth_status)
            gps.start(minTime=1000, minDistance=0)

    def update_blinker_position(self, *args, **kwargs):
        my_lat = kwargs['lat']
        my_lon = kwargs['lon']
        print("GPS POSITION", my_lat, my_lon)
        # Update GpsBlinker position
        gps_blinker = MDApp.get_running_app().root.ids.mapview.ids.blinker
        gps_blinker.lat = my_lat
        gps_blinker.lon = my_lon

        # center map on gpsblinker
        if not self.has_centered_map:
            map = MDApp.get_running_app().root.ids.mapview
            map.center_on(my_lat, my_lon)
            self.has_centered_map = True

    def on_auth_status(self, general_status, status_message):
        if general_status == 'provider-enabled':
            pass
        else:
            self.open_gps_access_popup()

    def open_gps_access_popup(self):
        dialog = MDDialog(title="GPS Error", text="You need to turn on location services for your device")
        dialog.size_hint = [.8, .8]
        dialog.pos_hint = {'center_x': .5, 'center_y': .5}
        dialog.open()

class MapViewClass(MapView):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._line_layer = None
        self.gmaps = googlemaps.Client(key=MAP_API_KEY)

        my_origin = "4.1506595505986645,9.30054799695078"
        my_destination = "4.149268458906271,9.287887970242025"
        # self.get_directions(my_origin, my_destination)

        self.getting_markers_timer = None
        self.marker_names = []

    @property
    def line_layer(self):
        if self._line_layer is None:
            self._line_layer = LineMapLayer()
            # self.ids.mapview.add_layer(self._line_layer, mode='scatter')
            self.add_layer(self._line_layer, mode='scatter')

        return self._line_layer

    def get_directions(self, fromAddr, toAddr):
        Logger.info(f'Getting directions from {fromAddr!r} to {toAddr!r}...')
        try:
            routes = self.gmaps.directions(
                fromAddr,
                toAddr,
                mode='driving',
                departure_time=datetime.now()
            )

            route = routes[0]
            self.line_layer.coordinates = polyline.decode(route['overview_polyline']['points'])

            bounds = route['bounds']
            minBound = bounds['southwest']['lat'], bounds['southwest']['lng']
            maxBound = bounds['northeast']['lat'], bounds['northeast']['lng']
            self.fit(minBound, maxBound)

        except googlemaps.exceptions.HTTPError as err:
            Logger.warn(f'Error from Google Maps API: {err}')

    def fit(self, *points):
        minX, minY = float('inf'), float('inf')
        maxX, maxY = float('-inf'), float('-inf')
        for (x, y) in points:
            minX = min(minX, x)
            minY = min(minY, y)
            maxX = max(minX, x)
            maxY = max(minY, y)

        # self.ids.mapview.center_on((minX + maxX) / 2, (minY + maxY) / 2)
        self.center_on((minX + maxX) / 2, (minY + maxY) / 2)

    def start_getting_markers_in_fov(self):
        # After one second, get the markets in the field of view
        try:
            self.getting_markers_timer.cancel()
        except:
            pass

        self.getting_markers_timer = Clock.schedule_once(self.get_markers_in_fov, 1)

    def get_markers_in_fov(self, *args):
        # Get reference to main app and the database cursor
        min_lat, min_lon, max_lat, max_lon = self.get_bbox()
        app = MDApp.get_running_app()

        lng_lat = {'Mile 17': [4.1506595505986645, 9.30054799695078], 'GCE Board': [4.161167564109226, 9.27561418277514], 'Central Admin UB': [4.149268458906271, 9.287887970242025], 'Mountain Ice Cream': [4.149289860272598, 9.261988560666916]}

        for location_name, location_data in lng_lat.items():
            name = location_name
            if name in self.marker_names:
                continue
            else:
                self.add_markers(location_name, location_data)

    def add_markers(self, location_name, location_data):
        # Create the MarketMarker
        lat, lon = location_data[0], location_data[1]
        place_image = "dummy.jpeg"
        # print(f"Lat: {lat} and Lon: {lon}")
        marker = MapMarkerClass(lat=lat, lon=lon, source="marker.png", image_src=place_image, label_one=location_name, label_two='Here will be some data about this location')

        # Add the MarketMarker to the map
        self.add_widget(marker)

        # Keep track of the marker's name
        name = location_name
        self.marker_names.append(name)

class MainApp(MDApp):
    connection = None
    cursor = None
    search_menu = None


    def on_start(self):
        self.theme_cls.primary_palette = 'BlueGray'
        GpsHelper().run()

    def get_new_dir(self):
        map = MapViewClass()
        print(map)
        my_origin = "4.1506595505986645,9.30054799695078"
        my_destination = "4.149289860272598,9.261988560666916"
        map.get_directions(my_origin, my_destination)

MainApp().run()
