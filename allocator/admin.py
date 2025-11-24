from django.contrib import admin
from .models import (
    Job, TaskAllocation, WriterProfile, ProcessTeamProfile,
    JobQuery, AllocationHistory, CountryBankingResource
)


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ['masking_id', 'title', 'job_category', 'status', 'word_count', 'deadline', 'created_by', 'allocated_by']
    list_filter = ['status', 'job_category', 'priority', 'degree', 'created_at']
    search_fields = ['masking_id', 'title', 'topic', 'client_name']
    readonly_fields = ['masking_id', 'created_at', 'updated_at', 'allocated_at']
    
    fieldsets = (
        ('Job Information', {
            'fields': ('masking_id', 'title', 'topic', 'client_name', 'job_category', 'software_type', 'degree')
        }),
        ('Content Details', {
            'fields': ('word_count', 'max_word_limit', 'description', 'special_instructions')
        }),
        ('Status & Priority', {
            'fields': ('status', 'priority', 'has_query', 'query_count')
        }),
        ('Comments', {
            'fields': ('marketing_comment', 'allocator_comment', 'allocator_comment_approved')
        }),
        ('Assignment', {
            'fields': ('created_by', 'allocated_by')
        }),
        ('Files', {
            'fields': ('attachment', 'structure_file')
        }),
        ('Additional Info', {
            'fields': ('country', 'banking_sector')
        }),
        ('Timestamps', {
            'fields': ('deadline', 'created_at', 'updated_at', 'allocated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(TaskAllocation)
class TaskAllocationAdmin(admin.ModelAdmin):
    list_display = ['job', 'task_type', 'allocated_to', 'status', 'start_date_time', 'end_date_time']
    list_filter = ['task_type', 'status', 'allocated_at']
    search_fields = ['job__masking_id', 'allocated_to__email', 'allocated_to__first_name', 'allocated_to__last_name']
    readonly_fields = ['allocated_at', 'completed_at']
    
    fieldsets = (
        ('Task Information', {
            'fields': ('job', 'task_type', 'status')
        }),
        ('Assignment', {
            'fields': ('allocated_to', 'allocated_by')
        }),
        ('Timeline', {
            'fields': ('start_date_time', 'end_date_time', 'allocated_at', 'completed_at')
        }),
        ('Files', {
            'fields': ('submission_file', 'ai_summary_file', 'final_file')
        }),
        ('Quality Check', {
            'fields': ('temperature_matched', 'temperature_score')
        }),
    )


@admin.register(WriterProfile)
class WriterProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'is_it_writer', 'is_available', 'current_jobs', 'max_jobs', 'current_words', 'max_words', 'rating']
    list_filter = ['is_it_writer', 'is_nonit_writer', 'is_finance_writer', 'is_available', 'is_sunday_off', 'is_on_holiday', 'is_overloaded']
    search_fields = ['user__email', 'user__first_name', 'user__last_name', 'user__employee_id']
    
    fieldsets = (
        ('Writer Information', {
            'fields': ('user',)
        }),
        ('Specialization', {
            'fields': ('is_it_writer', 'is_nonit_writer', 'is_finance_writer')
        }),
        ('Availability', {
            'fields': ('is_available', 'is_sunday_off', 'is_on_holiday', 'is_overloaded')
        }),
        ('Capacity', {
            'fields': ('max_jobs', 'current_jobs', 'max_words', 'current_words')
        }),
        ('Performance', {
            'fields': ('total_jobs_completed', 'total_jobs_assigned', 'rating')
        }),
    )


@admin.register(ProcessTeamProfile)
class ProcessTeamProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'is_available', 'current_jobs', 'max_jobs', 'total_jobs_completed']
    list_filter = ['is_available', 'is_sunday_off', 'is_on_holiday']
    search_fields = ['user__email', 'user__first_name', 'user__last_name']


@admin.register(JobQuery)
class JobQueryAdmin(admin.ModelAdmin):
    list_display = ['job', 'raised_by', 'status', 'created_at', 'resolved_by', 'resolved_at']
    list_filter = ['status', 'created_at', 'resolved_at']
    search_fields = ['job__masking_id', 'raised_by__email', 'query_text']
    readonly_fields = ['created_at', 'resolved_at']


@admin.register(AllocationHistory)
class AllocationHistoryAdmin(admin.ModelAdmin):
    list_display = ['task_allocation', 'action', 'previous_user', 'new_user', 'changed_by', 'timestamp']
    list_filter = ['action', 'timestamp']
    search_fields = ['task_allocation__job__masking_id', 'changed_by__email']
    readonly_fields = ['timestamp']


@admin.register(CountryBankingResource)
class CountryBankingResourceAdmin(admin.ModelAdmin):
    list_display = ['country_name', 'created_at', 'updated_at']
    search_fields = ['country_name']
    readonly_fields = ['created_at', 'updated_at']