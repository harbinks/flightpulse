-- ============================================================================
-- FlightPulse Database Seed Data
-- Realistic baseline dataset for testing, analytics, and demonstration
-- ============================================================================

-- Clean existing data in reverse dependency order
TRUNCATE TABLE flight_events RESTART IDENTITY CASCADE;
TRUNCATE TABLE weather_observations RESTART IDENTITY CASCADE;
TRUNCATE TABLE news_events RESTART IDENTITY CASCADE;
TRUNCATE TABLE flights RESTART IDENTITY CASCADE;
TRUNCATE TABLE airlines RESTART IDENTITY CASCADE;
TRUNCATE TABLE airports RESTART IDENTITY CASCADE;

-- ============================================================================
-- 1. Seed Airports
-- ============================================================================
INSERT INTO airports (iata_code, icao_code, name, city, state, country, latitude, longitude, elevation_ft, timezone, data_source, source_record_id)
VALUES
('ATL', 'KATL', 'Hartsfield-Jackson Atlanta International Airport', 'Atlanta', 'Georgia', 'United States', 33.640728, -84.427700, 1026, 'America/New_York', 'FAA_AIRPORT_DIR', 'KATL-01'),
('ORD', 'KORD', 'Chicago O''Hare International Airport', 'Chicago', 'Illinois', 'United States', 41.974162, -87.907321, 672, 'America/Chicago', 'FAA_AIRPORT_DIR', 'KORD-01'),
('DFW', 'KDFW', 'Dallas/Fort Worth International Airport', 'Dallas', 'Texas', 'United States', 32.899809, -97.040335, 607, 'America/Chicago', 'FAA_AIRPORT_DIR', 'KDFW-01'),
('DEN', 'KDEN', 'Denver International Airport', 'Denver', 'Colorado', 'United States', 39.856096, -104.673738, 5431, 'America/Denver', 'FAA_AIRPORT_DIR', 'KDEN-01'),
('JFK', 'KJFK', 'John F. Kennedy International Airport', 'New York', 'New York', 'United States', 40.641311, -73.778139, 13, 'America/New_York', 'FAA_AIRPORT_DIR', 'KJFK-01'),
('LAX', 'KLAX', 'Los Angeles International Airport', 'Los Angeles', 'California', 'United States', 33.941589, -118.408530, 128, 'America/Los_Angeles', 'FAA_AIRPORT_DIR', 'KLAX-01'),
('SFO', 'KSFO', 'San Francisco International Airport', 'San Francisco', 'California', 'United States', 37.621313, -122.378955, 13, 'America/Los_Angeles', 'FAA_AIRPORT_DIR', 'KSFO-01'),
('LHR', 'EGLL', 'London Heathrow Airport', 'London', 'England', 'United Kingdom', 51.470020, -0.454295, 83, 'Europe/London', 'OURAIRPORTS', 'EGLL-01');

-- ============================================================================
-- 2. Seed Airlines
-- ============================================================================
INSERT INTO airlines (iata_code, icao_code, name, callsign, country, active, data_source, source_record_id)
VALUES
('DL', 'DAL', 'Delta Air Lines', 'DELTA', 'United States', TRUE, 'FAA_REGISTRY', 'AL-DL'),
('AA', 'AAL', 'American Airlines', 'AMERICAN', 'United States', TRUE, 'FAA_REGISTRY', 'AL-AA'),
('UA', 'UAL', 'United Airlines', 'UNITED', 'United States', TRUE, 'FAA_REGISTRY', 'AL-UA'),
('WN', 'SWA', 'Southwest Airlines', 'SOUTHWEST', 'United States', TRUE, 'FAA_REGISTRY', 'AL-WN'),
('BA', 'BAW', 'British Airways', 'SPEEDBIRD', 'United Kingdom', TRUE, 'CAA_REGISTRY', 'AL-BA');

-- ============================================================================
-- 3. Seed Flights
-- Reference IDs:
-- Airports: 1:ATL, 2:ORD, 3:DFW, 4:DEN, 5:JFK, 6:LAX, 7:SFO, 8:LHR
-- Airlines: 1:DL, 2:AA, 3:UA, 4:WN, 5:BA
-- ============================================================================
INSERT INTO flights (
    flight_number, airline_id, origin_airport_id, destination_airport_id,
    flight_date, scheduled_departure, actual_departure, scheduled_arrival, actual_arrival,
    status, departure_delay_minutes, arrival_delay_minutes, delay_category,
    tail_number, aircraft_type, distance_miles, data_source, source_record_id
)
VALUES
-- Flight 1: DL1042 ATL -> LGA/JFK (On-Time)
('DL1042', 1, 1, 5, '2026-10-04', '2026-10-04 12:00:00+00', '2026-10-04 12:03:00+00', '2026-10-04 14:15:00+00', '2026-10-04 14:10:00+00', 'LANDED', 3, -5, NULL, 'N342DN', 'A321', 760, 'FLIGHTAWARE', 'FA-DL1042-20261004'),

-- Flight 2: UA415 ORD -> DEN (Weather Delay at Origin - Thunderstorms)
('UA415', 3, 2, 4, '2026-10-04', '2026-10-04 14:30:00+00', '2026-10-04 16:15:00+00', '2026-10-04 17:05:00+00', '2026-10-04 18:42:00+00', 'LANDED', 105, 97, 'WEATHER', 'N77014', 'B772', 888, 'FLIGHTAWARE', 'FA-UA415-20261004'),

-- Flight 3: AA2401 DFW -> ORD (NAS Flow Control Delay arriving into ORD)
('AA2401', 2, 3, 2, '2026-10-04', '2026-10-04 15:00:00+00', '2026-10-04 15:45:00+00', '2026-10-04 17:25:00+00', '2026-10-04 18:18:00+00', 'LANDED', 45, 53, 'NAS', 'N821AA', 'B738', 802, 'FLIGHTAWARE', 'FA-AA2401-20261004'),

-- Flight 4: WN1892 DEN -> LAX (Late Aircraft Delay cascade)
('WN1892', 4, 4, 6, '2026-10-04', '2026-10-04 18:00:00+00', '2026-10-04 18:35:00+00', '2026-10-04 19:40:00+00', '2026-10-04 20:08:00+00', 'LANDED', 35, 28, 'LATE_AIRCRAFT', 'N419WN', 'B737', 862, 'FLIGHTAWARE', 'FA-WN1892-20261004'),

-- Flight 5: UA882 SFO -> ORD (Cancelled due to severe ground stop at ORD)
('UA882', 3, 7, 2, '2026-10-04', '2026-10-04 16:00:00+00', NULL, '2026-10-04 22:10:00+00', NULL, 'CANCELLED', 0, 0, 'WEATHER', 'N57863', 'B772', 1846, 'FLIGHTAWARE', 'FA-UA882-20261004'),

-- Flight 6: BA178 JFK -> LHR (Transatlantic On-Time)
('BA178', 5, 5, 8, '2026-10-04', '2026-10-04 23:00:00+00', '2026-10-04 23:12:00+00', '2026-10-05 06:45:00+00', '2026-10-05 06:35:00+00', 'LANDED', 12, -10, NULL, 'G-ZBKA', 'B789', 3451, 'FLIGHTAWARE', 'FA-BA178-20261004'),

-- Flight 7: DL210 ATL -> SFO (En Route / Active)
('DL210', 1, 1, 7, '2026-10-05', '2026-10-05 16:30:00+00', '2026-10-05 16:42:00+00', '2026-10-05 21:45:00+00', NULL, 'EN_ROUTE', 12, 0, NULL, 'N801DN', 'A359', 2139, 'FLIGHTAWARE', 'FA-DL210-20261005'),

-- Flight 8: AA100 JFK -> LHR (Scheduled Future)
('AA100', 2, 5, 8, '2026-10-05', '2026-10-05 22:30:00+00', NULL, '2026-10-06 06:30:00+00', NULL, 'SCHEDULED', 0, 0, NULL, 'N758AA', 'B772', 3451, 'FLIGHTAWARE', 'FA-AA100-20261005');

-- ============================================================================
-- 4. Seed Weather Observations (METAR Data)
-- ============================================================================
INSERT INTO weather_observations (
    airport_id, observation_time, temperature_c, dewpoint_c,
    wind_speed_knots, wind_gust_knots, wind_direction_deg, visibility_miles,
    altimeter_inhg, condition_code, raw_metar, data_source, source_record_id
)
VALUES
-- ORD Severe Thunderstorm Afternoon (correlating with UA415 delay and UA882 cancellation)
(2, '2026-10-04 13:51:00+00', 22.0, 18.0, 16.0, 24.0, 260, 9.00, 29.85, 'SCATTERED_CLOUDS', 'KORD 041351Z 26016G24KT 9SM SCT040 22/18 A2985 RMK AO2', 'NOAA_METAR', 'METAR-ORD-1351'),
(2, '2026-10-04 14:51:00+00', 19.5, 17.0, 28.0, 42.0, 290, 2.50, 29.74, 'THUNDERSTORM', 'KORD 041451Z 29028G42KT 2 1/2SM +TSRA BKN015CB 19/17 A2974 RMK AO2 PK WND 29045/48', 'NOAA_METAR', 'METAR-ORD-1451'),
(2, '2026-10-04 15:51:00+00', 18.0, 16.5, 22.0, 34.0, 310, 4.00, 29.79, 'RAIN', 'KORD 041551Z 31022G34KT 4SM RA OVC020 18/16 A2979 RMK AO2', 'NOAA_METAR', 'METAR-ORD-1551'),
(2, '2026-10-04 16:51:00+00', 17.0, 14.0, 14.0, NULL, 320, 10.00, 29.88, 'OVERCAST', 'KORD 041651Z 32014KT 10SM OVC045 17/14 A2988 RMK AO2', 'NOAA_METAR', 'METAR-ORD-1651'),

-- DEN Clear & Gusty
(4, '2026-10-04 16:53:00+00', 16.0, -2.0, 14.0, 22.0, 180, 10.00, 30.12, 'CLEAR', 'KDEN 041653Z 18014G22KT 10SM CLR 16/M02 A3012 RMK AO2', 'NOAA_METAR', 'METAR-DEN-1653'),
(4, '2026-10-04 18:53:00+00', 14.0, -1.0, 12.0, NULL, 170, 10.00, 30.10, 'CLEAR', 'KDEN 041853Z 17012KT 10SM CLR 14/M01 A3010 RMK AO2', 'NOAA_METAR', 'METAR-DEN-1853'),

-- ATL Calm
(1, '2026-10-04 11:52:00+00', 21.0, 12.0, 6.0, NULL, 90, 10.00, 30.05, 'CLEAR', 'KATL 041152Z 09006KT 10SM FEW050 21/12 A3005 RMK AO2', 'NOAA_METAR', 'METAR-ATL-1152'),

-- JFK Standard
(5, '2026-10-04 22:51:00+00', 18.0, 13.0, 11.0, NULL, 150, 10.00, 30.01, 'CLEAR', 'KJFK 042251Z 15011KT 10SM FEW040 18/13 A3001 RMK AO2', 'NOAA_METAR', 'METAR-JFK-2251');

-- ============================================================================
-- 5. Seed News Events
-- ============================================================================
INSERT INTO news_events (
    title, summary, source, url, event_type, severity, airport_id, airline_id,
    start_time, end_time, data_source, source_record_id
)
VALUES
(
    'FAA Ground Stop: Chicago O''Hare (ORD) Severe Convective Storms',
    'FAA issued a full ground stop for all inbound and departing traffic at Chicago O''Hare due to strong thunderstorm activity and high wind gusts exceeding 40 knots across all arrival corridors.',
    'FAA Air Traffic Control System Command Center',
    'https://nasstatus.faa.gov/api/ground-stops/ORD-20261004-01',
    'GROUND_STOP',
    'CRITICAL',
    2,
    NULL,
    '2026-10-04 14:15:00+00',
    '2026-10-04 16:00:00+00',
    'FAA_ATCSCC',
    'NOTAM-ORD-20261004-01'
),
(
    'Midwest En-Route Air Traffic Management Ground Delay Program',
    'Due to volume and weather avoidance around Chicago Center airspace (ZAU), arrival delays for flights into ORD are averaging 52 minutes.',
    'FAA ATCSCC Advisory',
    'https://nasstatus.faa.gov/api/advisories/20261004-082',
    'SEVERE_WEATHER_ALERT',
    'HIGH',
    2,
    NULL,
    '2026-10-04 14:00:00+00',
    '2026-10-04 18:30:00+00',
    'FAA_ATCSCC',
    'ADV-ZAU-20261004-82'
),
(
    'Southwest Airlines Fleet Turnaround Congestion at Denver (DEN)',
    'Cascading turnaround delays reported across gate concourses C and B at DEN following late inbound arrivals from upper Midwest routes.',
    'Aviation Herald Dispatch',
    'https://avherald.com/disruptions/den-cascades-20261004',
    'GENERAL_DISRUPTION',
    'LOW',
    4,
    4,
    '2026-10-04 17:00:00+00',
    '2026-10-04 20:00:00+00',
    'NEWS_SCRAPER',
    'AVH-20261004-DEN'
);

-- ============================================================================
-- 6. Seed Flight Events (Lifecycle Auditing for UA415)
-- Flight ID 2 corresponds to UA415 (ORD -> DEN)
-- ============================================================================
INSERT INTO flight_events (flight_id, event_type, event_time, description, metadata, data_source, source_record_id)
VALUES
(
    2,
    'SCHEDULED',
    '2026-10-04 06:00:00+00',
    'Flight schedule loaded into dispatch system',
    '{"gate": "C16", "terminal": "1", "crew_assigned": true}'::jsonb,
    'UA_INTERNAL_DISPATCH',
    'EVT-UA415-01'
),
(
    2,
    'GATE_CHANGE',
    '2026-10-04 13:40:00+00',
    'Departure gate changed from C16 to C22',
    '{"old_gate": "C16", "new_gate": "C22", "terminal": "1"}'::jsonb,
    'AIRPORT_FIDS',
    'EVT-UA415-02'
),
(
    2,
    'DELAY_UPDATE',
    '2026-10-04 14:20:00+00',
    'Departure delay announced due to FAA ORD ground stop',
    '{"initial_delay_minutes": 60, "reason": "FAA Ground Stop - Thunderstorms", "estimated_departure": "2026-10-04T15:30:00Z"}'::jsonb,
    'FAA_SWIM',
    'EVT-UA415-03'
),
(
    2,
    'DELAY_UPDATE',
    '2026-10-04 15:15:00+00',
    'Ground stop extended; departure delayed an additional 45 minutes',
    '{"revised_delay_minutes": 105, "reason": "Severe Weather Runway Congestion", "estimated_departure": "2026-10-04T16:15:00Z"}'::jsonb,
    'FAA_SWIM',
    'EVT-UA415-04'
),
(
    2,
    'TAXI_OUT',
    '2026-10-04 16:15:00+00',
    'Aircraft pushed back from gate C22 and commenced taxi',
    '{"runway": "28R", "fuel_on_board_lbs": 34200}'::jsonb,
    'ACARS_DOWNLINK',
    'EVT-UA415-05'
),
(
    2,
    'AIRBORNE',
    '2026-10-04 16:32:00+00',
    'Wheels off from runway 28R',
    '{"actual_wheels_off": "2026-10-04T16:32:00Z", "heading_deg": 275}'::jsonb,
    'ADS_B_NETWORK',
    'EVT-UA415-06'
),
(
    2,
    'LANDED',
    '2026-10-04 18:42:00+00',
    'Flight arrived and docked at gate B32 in Denver',
    '{"arrival_gate": "B32", "wheels_down": "2026-10-04T18:35:00Z"}'::jsonb,
    'ACARS_DOWNLINK',
    'EVT-UA415-07'
);
