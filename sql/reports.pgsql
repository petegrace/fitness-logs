-- Active users report
with cte_events as
(
    select user_id, cast(created_datetime as date) as event_date
    from activity
    union all
    select user_id, cast(created_datetime as date) as event_date
    from scheduled_activity
    union all
    select et.user_id, cast(e.created_datetime as date) as event_date
    from exercise_type et
    inner join exercise e on et.id = e.exercise_type_id
    union all
    select et.user_id, cast(e.created_datetime as date) as event_date
    from exercise_type et
    inner join scheduled_exercise e on et.id = e.exercise_type_id
),
cte_events_with_user_visits as
(
    select user_id, event_date,
           dense_rank() over (partition by user_id order by event_date) as user_visit_number
    from cte_events
),
cte_events_per_user_per_week as
(
    select cal.calendar_week_start_date, user_id, min(user_visit_number) as user_visit_number
    from cte_events_with_user_visits e
    inner join public.calendar_day cal on e.event_date = cal.calendar_date
    group by cal.calendar_week_start_date, user_id
)
select calendar_week_start_date, user_visit_number, count(distinct user_id)
from cte_events_per_user_per_week
group by calendar_week_start_date, user_visit_number
order by calendar_week_start_date desc, user_visit_number desc

-- Logins in last week
select *
from public.user
where last_login_datetime >= current_date - interval '7 day'
  and last_login_datetime >= cast(created_datetime as date) + interval '1 day'
and id not in (1, 173)
order by id desc

-- Email subscribers
select email, coalesce(first_name, '') as first_name, coalesce(last_name, '') as last_name
from public.user
where is_opted_in_for_marketing_emails = true
  and email not like 'DEL%'