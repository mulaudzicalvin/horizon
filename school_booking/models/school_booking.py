# -*- encoding: utf-8 -*-
##############################################################################
#
#    Copyright (c) 2015 be-cloud.be
#                       Jerome Sonnet <jerome.sonnet@be-cloud.be>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
import logging

from datetime import datetime, date, time, timedelta

from openerp import api, fields, models, _, tools
from openerp.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class Year(models.Model):
    _inherit = 'school.year'
    
    calendar_id = fields.Many2one('school.calendar', string='Default Calendar')

class SchoolCalendar(models.Model):
    _name = 'school.calendar'
    
    name = fields.Char(string='Name')
    active = fields.Boolean(string='Active')
    
    year_id = fields.Many2one('school.year', string='Year', default=lambda self: self.env.user.current_year_id)
    from_date = fields.Date('From Date')
    to_date = fields.Date('From Date')
    leave_ids = fields.One2many('school.calendar.leave', 'calendar_id', 'Leaves',help='')
    
class SchoolLeave(models.Model):
    _name = 'school.calendar.leave'

    calendar_id = fields.Many2one('school.calendar', string='Calendar')

    from_date = fields.Date('From Date')
    to_date = fields.Date('From Date')

    partner_id = fields.Many2one('res.partner', string='Partner', help="If set, the leave is only for the specified partner.")
    asset_id = fields.Many2one('school.asset', string='Asset', help="If set, the leave is only for the asset.")
    category_id = fields.Many2one('school.asset.category', string='Category', help="If set, the leave is only for the asset of this category.")

class Event(models.Model):
    """ Model for School Event """
    _inherit = 'calendar.event'
    
    group_id = fields.Many2one('school.student_group', string='Group', ondelete='set null')
    yearly_booking_id = fields.Many2one('school.yearly_booking', string='Group', ondelete='set null')
    
    room_id = fields.Many2one('school.asset', string='Room')
    asset_ids = fields.Many2many('school.asset', 'event_assets_ref','event_id','asset_id', string='Assets')
    
    main_categ_id = fields.Many2one('calendar.event.type', compute='_get_main_categ_id')
    
    @api.one
    def _get_main_categ_id(self):
        if self.categ_ids:
            self.main_categ_id = self.categ_ids[0]
            
    @api.one
    @api.constrains('room_id')
    def _check_room_quota(self):
        if self.user_id.partner_id.teacher or self.user_id.partner_id.employee :
            return
        
        # Prevent concurrent bookings
        
        conflicts_count = self.env['calendar.event'].search_count([('room_id','=',self.room_id.id), ('start', '<=', fields.Datetime.to_string(self.end)), ('stop', '>=', fields.Datetime.to_string(self.stop))])
        
        if conflicts_count > 0:
            raise ValidationError(_("Concurrent event detected"))
        
        # Constraint on student events
        
        student_event = self.env['ir.model.data'].xmlid_to_object('school_booking.school_student_event_type')
        
        if student_event in self.categ_ids:
            now = datetime.now()
            if now.hour < 11 and fields.Datetime.from_string(self.start_datetime).date() != now.date() :
                raise ValidationError(_("You cannot book for the next day before 12h00."))
            
            if now.hour >= 11 and fields.Datetime.from_string(self.start_datetime).date() != now.date() and fields.Datetime.from_string(self.start_datetime).date() != (now + timedelta(days=1)).date() :
                raise ValidationError(_("You can book only the next day (after 12h00)."))
            
            event_day = fields.Datetime.from_string(self.start_datetime).date()
            
            duration_list = self.env['calendar.event'].read_group([
                    ('user_id', '=', self.user_id.id), ('categ_ids','in',student_event.id), ('start', '>', fields.Datetime.to_string(event_day)), ('start', '<', fields.Datetime.to_string(event_day + timedelta(days=1)))
                ],['room_id','duration'],['room_id'])
            _logger.info(duration_list)
            for duration in duration_list:
                if duration['duration'] and duration['duration'] > 2:
                    raise ValidationError(_("You cannot book the room %s more than two hours per day") % (duration.get('room_id','')[1]))
            
            duration_list = self.env['calendar.event'].read_group([
                    ('user_id', '=', self.user_id.id), ('categ_ids','in',student_event.id), ('start', '>', fields.Datetime.to_string(event_day)), ('start', '<', fields.Datetime.to_string(event_day + timedelta(days=1)))
                ],['start_datetime','duration'],['start_datetime:day'])
            _logger.info(duration_list)
            for duration in duration_list:
                if duration['duration'] and duration['duration'] > 6:
                    raise ValidationError(_("You cannot book more than six hours per day - %s") % duration['start_datetime:day'])
            
            duration_list = self.env['calendar.event'].read_group([
                    ('user_id', '=', self.user_id.id), ('start', '>', fields.Datetime.now()), ('categ_ids','in',student_event.id), ('start', '>', fields.Datetime.to_string(event_day)), ('start', '<', fields.Datetime.to_string(event_day + timedelta(days=1)))
                ],['start_datetime','duration'],['start_datetime:day'])
            for duration in duration_list:
                if duration['duration'] > 4:
                    raise ValidationError(_("You cannot book more than four hours in advance per day - %s") % duration['start_datetime:day'])
                    
            