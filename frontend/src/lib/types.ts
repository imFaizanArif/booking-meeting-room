export type UserRole = "employee" | "admin";
export type BookingStatus = "pending" | "confirmed" | "rejected" | "cancelled";

export interface Profile {
  id: string;
  name: string;
  email: string;
  department: string;
  designation: string;
  avatar_url: string | null;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface Room {
  id: string;
  name: string;
  capacity: number;
  floor: number;
  description: string;
  image_url: string | null;
  color: string;
  is_active: boolean;
  created_at: string;
}

export interface Attendee {
  id: string;
  booking_id: string;
  user_id: string;
  user: Profile | null;
}

export interface Booking {
  id: string;
  room_id: string;
  user_id: string;
  title: string;
  purpose: string;
  start_time: string;
  end_time: string;
  status: BookingStatus;
  created_at: string;
  room: Room | null;
  user: Profile | null;
  attendees: Attendee[];
}

export interface RoomUtilization {
  room_id: string;
  room_name: string;
  color: string;
  booked_hours: number;
  bookings_count: number;
  utilization_pct: number;
}

export interface DashboardStats {
  total_bookings: number;
  active_rooms: number;
  total_users: number;
  upcoming_meetings: number;
  pending_approvals: number;
  room_utilization: RoomUtilization[];
  bookings_per_day: { date: string; count: number }[];
}

export interface BookingPayload {
  room_id: string;
  title: string;
  purpose: string;
  start_time: string;
  end_time: string;
  attendee_ids: string[];
}

export interface RoomPayload {
  name: string;
  capacity: number;
  floor: number;
  description: string;
  image_url?: string | null;
  color: string;
  is_active: boolean;
}
