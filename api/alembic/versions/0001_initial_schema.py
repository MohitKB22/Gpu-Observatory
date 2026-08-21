"""initial schema

Revision ID: 0001_initial
Revises: 
Create Date: 2026-08-13 14:57:15.451759
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Initial schema for NVIDIA AI Performance Observatory.
    op.create_table('alert_rules',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('condition', sa.String(length=60), nullable=False),
    sa.Column('threshold', sa.Float(), nullable=False),
    sa.Column('severity', sa.String(length=16), nullable=False),
    sa.Column('entity_type', sa.String(length=40), nullable=True),
    sa.Column('entity_id', sa.String(length=36), nullable=True),
    sa.Column('for_seconds', sa.Integer(), nullable=False),
    sa.Column('cooldown_seconds', sa.Integer(), nullable=False),
    sa.Column('is_enabled', sa.Boolean(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('data_source', sa.String(length=16), nullable=False),
    sa.Column('last_fired_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_alert_rules'))
    )
    with op.batch_alter_table('alert_rules', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_alert_rules_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_alert_rules_data_source'), ['data_source'], unique=False)
        batch_op.create_index(batch_op.f('ix_alert_rules_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_alert_rules_is_enabled'), ['is_enabled'], unique=False)
        batch_op.create_index(batch_op.f('ix_alert_rules_name'), ['name'], unique=False)

    op.create_table('anomalies',
    sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('metric_kind', sa.String(length=40), nullable=False),
    sa.Column('method', sa.String(length=30), nullable=False),
    sa.Column('severity', sa.String(length=16), nullable=False),
    sa.Column('data_source', sa.String(length=16), nullable=False),
    sa.Column('entity_type', sa.String(length=40), nullable=True),
    sa.Column('entity_id', sa.String(length=36), nullable=True),
    sa.Column('entity_label', sa.String(length=200), nullable=True),
    sa.Column('observed_value', sa.Float(), nullable=False),
    sa.Column('expected_value', sa.Float(), nullable=True),
    sa.Column('deviation', sa.Float(), nullable=True),
    sa.Column('score', sa.Float(), nullable=True),
    sa.Column('threshold', sa.Float(), nullable=True),
    sa.Column('window_seconds', sa.Integer(), nullable=True),
    sa.Column('sample_count', sa.Integer(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_anomalies'))
    )
    with op.batch_alter_table('anomalies', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_anomalies_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_anomalies_data_source'), ['data_source'], unique=False)
        batch_op.create_index(batch_op.f('ix_anomalies_detected_at'), ['detected_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_anomalies_entity_id'), ['entity_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_anomalies_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_anomalies_metric_kind'), ['metric_kind'], unique=False)
        batch_op.create_index('ix_anomalies_metric_time', ['metric_kind', 'detected_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_anomalies_severity'), ['severity'], unique=False)
        batch_op.create_index('ix_anomalies_source_time', ['data_source', 'detected_at'], unique=False)

    op.create_table('audit_logs',
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('actor_type', sa.String(length=20), nullable=False),
    sa.Column('actor_id', sa.String(length=36), nullable=True),
    sa.Column('actor_label', sa.String(length=320), nullable=True),
    sa.Column('action', sa.String(length=80), nullable=False),
    sa.Column('resource_type', sa.String(length=60), nullable=True),
    sa.Column('resource_id', sa.String(length=64), nullable=True),
    sa.Column('outcome', sa.String(length=20), nullable=False),
    sa.Column('request_id', sa.String(length=64), nullable=True),
    sa.Column('source_ip', sa.String(length=64), nullable=True),
    sa.Column('detail', sa.Text(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_logs'))
    )
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.create_index('ix_audit_action_time', ['action', 'occurred_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_logs_action'), ['action'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_logs_actor_id'), ['actor_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_logs_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_logs_occurred_at'), ['occurred_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_logs_request_id'), ['request_id'], unique=False)

    op.create_table('diagnoses',
    sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('kind', sa.String(length=50), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('severity', sa.String(length=16), nullable=False),
    sa.Column('engine', sa.String(length=20), nullable=False),
    sa.Column('data_source', sa.String(length=16), nullable=False),
    sa.Column('entity_type', sa.String(length=40), nullable=True),
    sa.Column('entity_id', sa.String(length=36), nullable=True),
    sa.Column('entity_label', sa.String(length=200), nullable=True),
    sa.Column('root_cause', sa.Text(), nullable=False),
    sa.Column('evidence', sa.Text(), nullable=False),
    sa.Column('metrics', sa.Text(), nullable=False),
    sa.Column('impact', sa.Text(), nullable=True),
    sa.Column('recommendations', sa.Text(), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('window_seconds', sa.Integer(), nullable=True),
    sa.Column('narrative', sa.Text(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_diagnoses'))
    )
    with op.batch_alter_table('diagnoses', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_diagnoses_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_diagnoses_data_source'), ['data_source'], unique=False)
        batch_op.create_index(batch_op.f('ix_diagnoses_entity_id'), ['entity_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_diagnoses_generated_at'), ['generated_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_diagnoses_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_diagnoses_kind'), ['kind'], unique=False)
        batch_op.create_index(batch_op.f('ix_diagnoses_severity'), ['severity'], unique=False)
        batch_op.create_index('ix_diagnoses_source_time', ['data_source', 'generated_at'], unique=False)

    op.create_table('gpus',
    sa.Column('uuid', sa.String(length=96), nullable=False),
    sa.Column('index', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('host', sa.String(length=200), nullable=False),
    sa.Column('driver_version', sa.String(length=60), nullable=True),
    sa.Column('cuda_version', sa.String(length=30), nullable=True),
    sa.Column('vbios_version', sa.String(length=60), nullable=True),
    sa.Column('serial', sa.String(length=60), nullable=True),
    sa.Column('total_memory_mb', sa.Float(), nullable=True),
    sa.Column('power_limit_w', sa.Float(), nullable=True),
    sa.Column('max_clock_mhz', sa.Integer(), nullable=True),
    sa.Column('max_memory_clock_mhz', sa.Integer(), nullable=True),
    sa.Column('compute_capability', sa.String(length=16), nullable=True),
    sa.Column('pcie_gen', sa.Integer(), nullable=True),
    sa.Column('pcie_width', sa.Integer(), nullable=True),
    sa.Column('data_source', sa.String(length=16), nullable=False),
    sa.Column('is_available', sa.Boolean(), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_gpus')),
    sa.UniqueConstraint('uuid', 'data_source', name='uq_gpus_uuid_source')
    )
    with op.batch_alter_table('gpus', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_gpus_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_gpus_data_source'), ['data_source'], unique=False)
        batch_op.create_index(batch_op.f('ix_gpus_host'), ['host'], unique=False)
        batch_op.create_index(batch_op.f('ix_gpus_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_gpus_last_seen_at'), ['last_seen_at'], unique=False)
        batch_op.create_index('ix_gpus_source_index', ['data_source', 'index'], unique=False)
        batch_op.create_index(batch_op.f('ix_gpus_uuid'), ['uuid'], unique=False)

    op.create_table('ml_models',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('version', sa.String(length=60), nullable=False),
    sa.Column('display_name', sa.String(length=200), nullable=True),
    sa.Column('framework', sa.String(length=30), nullable=False),
    sa.Column('parameter_count_b', sa.Float(), nullable=True),
    sa.Column('quantization', sa.String(length=20), nullable=False),
    sa.Column('context_length', sa.Integer(), nullable=True),
    sa.Column('max_batch_size', sa.Integer(), nullable=True),
    sa.Column('preferred_batch_sizes', sa.String(length=120), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('tags', sa.String(length=300), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('data_source', sa.String(length=16), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ml_models')),
    sa.UniqueConstraint('name', 'version', 'data_source', name='uq_ml_models_name_version')
    )
    with op.batch_alter_table('ml_models', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ml_models_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_ml_models_data_source'), ['data_source'], unique=False)
        batch_op.create_index(batch_op.f('ix_ml_models_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ml_models_name'), ['name'], unique=False)

    op.create_table('pricing_profiles',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('gpu_model', sa.String(length=160), nullable=True),
    sa.Column('provider', sa.String(length=120), nullable=True),
    sa.Column('region', sa.String(length=80), nullable=True),
    sa.Column('cost_per_gpu_hour', sa.Float(), nullable=False),
    sa.Column('currency', sa.String(length=8), nullable=False),
    sa.Column('energy_cost_per_kwh', sa.Float(), nullable=True),
    sa.Column('amortization_months', sa.Integer(), nullable=True),
    sa.Column('hardware_capex', sa.Float(), nullable=True),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.Column('is_estimate', sa.Boolean(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('effective_from', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_pricing_profiles'))
    )
    with op.batch_alter_table('pricing_profiles', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pricing_profiles_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_pricing_profiles_gpu_model'), ['gpu_model'], unique=False)
        batch_op.create_index(batch_op.f('ix_pricing_profiles_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pricing_profiles_is_default'), ['is_default'], unique=False)
        batch_op.create_index(batch_op.f('ix_pricing_profiles_name'), ['name'], unique=False)

    op.create_table('system_metrics',
    sa.Column('host', sa.String(length=200), nullable=False),
    sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('data_source', sa.String(length=16), nullable=False),
    sa.Column('cpu_utilization_pct', sa.Float(), nullable=True),
    sa.Column('per_core_utilization', sa.Text(), nullable=True),
    sa.Column('core_count', sa.Integer(), nullable=True),
    sa.Column('load_avg_1m', sa.Float(), nullable=True),
    sa.Column('load_avg_5m', sa.Float(), nullable=True),
    sa.Column('load_avg_15m', sa.Float(), nullable=True),
    sa.Column('ram_total_mb', sa.Float(), nullable=True),
    sa.Column('ram_used_mb', sa.Float(), nullable=True),
    sa.Column('ram_utilization_pct', sa.Float(), nullable=True),
    sa.Column('swap_total_mb', sa.Float(), nullable=True),
    sa.Column('swap_used_mb', sa.Float(), nullable=True),
    sa.Column('disk_total_gb', sa.Float(), nullable=True),
    sa.Column('disk_used_gb', sa.Float(), nullable=True),
    sa.Column('disk_utilization_pct', sa.Float(), nullable=True),
    sa.Column('net_sent_kb_s', sa.Float(), nullable=True),
    sa.Column('net_recv_kb_s', sa.Float(), nullable=True),
    sa.Column('process_count', sa.Integer(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_system_metrics'))
    )
    with op.batch_alter_table('system_metrics', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_system_metrics_data_source'), ['data_source'], unique=False)
        batch_op.create_index(batch_op.f('ix_system_metrics_host'), ['host'], unique=False)
        batch_op.create_index('ix_system_metrics_host_time', ['host', 'recorded_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_system_metrics_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_system_metrics_recorded_at'), ['recorded_at'], unique=False)

    op.create_table('users',
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('full_name', sa.String(length=200), nullable=True),
    sa.Column('hashed_password', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('failed_login_count', sa.Integer(), nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_users_email'), ['email'], unique=True)
        batch_op.create_index(batch_op.f('ix_users_id'), ['id'], unique=False)
        batch_op.create_index('ix_users_role_active', ['role', 'is_active'], unique=False)

    op.create_table('alerts',
    sa.Column('rule_id', sa.String(length=36), nullable=True),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('condition', sa.String(length=60), nullable=False),
    sa.Column('severity', sa.String(length=16), nullable=False),
    sa.Column('state', sa.String(length=20), nullable=False),
    sa.Column('data_source', sa.String(length=16), nullable=False),
    sa.Column('entity_type', sa.String(length=40), nullable=True),
    sa.Column('entity_id', sa.String(length=36), nullable=True),
    sa.Column('entity_label', sa.String(length=200), nullable=True),
    sa.Column('observed_value', sa.Float(), nullable=True),
    sa.Column('threshold', sa.Float(), nullable=True),
    sa.Column('message', sa.Text(), nullable=True),
    sa.Column('triggered_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('acknowledged_by', sa.String(length=320), nullable=True),
    sa.Column('acknowledge_note', sa.Text(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolve_reason', sa.String(length=300), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['rule_id'], ['alert_rules.id'], name=op.f('fk_alerts_rule_id_alert_rules'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_alerts'))
    )
    with op.batch_alter_table('alerts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_alerts_condition'), ['condition'], unique=False)
        batch_op.create_index(batch_op.f('ix_alerts_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_alerts_data_source'), ['data_source'], unique=False)
        batch_op.create_index(batch_op.f('ix_alerts_entity_id'), ['entity_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_alerts_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_alerts_rule_id'), ['rule_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_alerts_severity'), ['severity'], unique=False)
        batch_op.create_index('ix_alerts_source_state', ['data_source', 'state'], unique=False)
        batch_op.create_index(batch_op.f('ix_alerts_state'), ['state'], unique=False)
        batch_op.create_index('ix_alerts_state_time', ['state', 'triggered_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_alerts_triggered_at'), ['triggered_at'], unique=False)

    op.create_table('api_keys',
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('prefix', sa.String(length=32), nullable=False),
    sa.Column('key_hash', sa.String(length=128), nullable=False),
    sa.Column('scopes', sa.Text(), nullable=False),
    sa.Column('owner_id', sa.String(length=36), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('rate_limit_per_minute', sa.Integer(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_api_keys_owner_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_api_keys'))
    )
    with op.batch_alter_table('api_keys', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_api_keys_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_api_keys_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_api_keys_key_hash'), ['key_hash'], unique=True)
        batch_op.create_index(batch_op.f('ix_api_keys_owner_id'), ['owner_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_api_keys_prefix'), ['prefix'], unique=False)

    op.create_table('deployments',
    sa.Column('model_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('environment', sa.String(length=40), nullable=False),
    sa.Column('gpu_id', sa.String(length=36), nullable=True),
    sa.Column('gpu_count', sa.Integer(), nullable=False),
    sa.Column('endpoint_url', sa.String(length=400), nullable=True),
    sa.Column('backend', sa.String(length=30), nullable=False),
    sa.Column('replicas', sa.Integer(), nullable=False),
    sa.Column('max_batch_size', sa.Integer(), nullable=True),
    sa.Column('batch_window_ms', sa.Float(), nullable=True),
    sa.Column('tensor_parallel_size', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('model_load_time_ms', sa.Float(), nullable=True),
    sa.Column('data_source', sa.String(length=16), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['gpu_id'], ['gpus.id'], name=op.f('fk_deployments_gpu_id_gpus'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['model_id'], ['ml_models.id'], name=op.f('fk_deployments_model_id_ml_models'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_deployments')),
    sa.UniqueConstraint('name', 'environment', 'data_source', name='uq_deployments_name_env')
    )
    with op.batch_alter_table('deployments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_deployments_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_deployments_data_source'), ['data_source'], unique=False)
        batch_op.create_index(batch_op.f('ix_deployments_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_deployments_model_id'), ['model_id'], unique=False)
        batch_op.create_index('ix_deployments_model_status', ['model_id', 'status'], unique=False)
        batch_op.create_index(batch_op.f('ix_deployments_status'), ['status'], unique=False)

    op.create_table('gpu_metrics',
    sa.Column('gpu_id', sa.String(length=36), nullable=False),
    sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('data_source', sa.String(length=16), nullable=False),
    sa.Column('utilization_pct', sa.Float(), nullable=True),
    sa.Column('memory_utilization_pct', sa.Float(), nullable=True),
    sa.Column('memory_used_mb', sa.Float(), nullable=True),
    sa.Column('memory_free_mb', sa.Float(), nullable=True),
    sa.Column('memory_total_mb', sa.Float(), nullable=True),
    sa.Column('temperature_c', sa.Float(), nullable=True),
    sa.Column('power_w', sa.Float(), nullable=True),
    sa.Column('power_limit_w', sa.Float(), nullable=True),
    sa.Column('sm_clock_mhz', sa.Integer(), nullable=True),
    sa.Column('memory_clock_mhz', sa.Integer(), nullable=True),
    sa.Column('fan_speed_pct', sa.Float(), nullable=True),
    sa.Column('pcie_tx_kb_s', sa.Float(), nullable=True),
    sa.Column('pcie_rx_kb_s', sa.Float(), nullable=True),
    sa.Column('throttle_reasons', sa.Text(), nullable=True),
    sa.Column('ecc_errors', sa.Integer(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['gpu_id'], ['gpus.id'], name=op.f('fk_gpu_metrics_gpu_id_gpus'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_gpu_metrics'))
    )
    with op.batch_alter_table('gpu_metrics', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_gpu_metrics_data_source'), ['data_source'], unique=False)
        batch_op.create_index(batch_op.f('ix_gpu_metrics_gpu_id'), ['gpu_id'], unique=False)
        batch_op.create_index('ix_gpu_metrics_gpu_time', ['gpu_id', 'recorded_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_gpu_metrics_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_gpu_metrics_recorded_at'), ['recorded_at'], unique=False)
        batch_op.create_index('ix_gpu_metrics_source_time', ['data_source', 'recorded_at'], unique=False)

    op.create_table('gpu_processes',
    sa.Column('gpu_id', sa.String(length=36), nullable=False),
    sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('pid', sa.Integer(), nullable=False),
    sa.Column('process_name', sa.String(length=255), nullable=True),
    sa.Column('used_memory_mb', sa.Float(), nullable=True),
    sa.Column('sm_utilization_pct', sa.Float(), nullable=True),
    sa.Column('workload_label', sa.String(length=160), nullable=True),
    sa.Column('data_source', sa.String(length=16), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['gpu_id'], ['gpus.id'], name=op.f('fk_gpu_processes_gpu_id_gpus'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_gpu_processes'))
    )
    with op.batch_alter_table('gpu_processes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_gpu_processes_data_source'), ['data_source'], unique=False)
        batch_op.create_index(batch_op.f('ix_gpu_processes_gpu_id'), ['gpu_id'], unique=False)
        batch_op.create_index('ix_gpu_processes_gpu_time', ['gpu_id', 'recorded_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_gpu_processes_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_gpu_processes_recorded_at'), ['recorded_at'], unique=False)

    op.create_table('refresh_tokens',
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('token_hash', sa.String(length=128), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('user_agent', sa.String(length=300), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_refresh_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_refresh_tokens'))
    )
    with op.batch_alter_table('refresh_tokens', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_refresh_tokens_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_refresh_tokens_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_refresh_tokens_token_hash'), ['token_hash'], unique=True)
        batch_op.create_index(batch_op.f('ix_refresh_tokens_user_id'), ['user_id'], unique=False)

    op.create_table('batch_metrics',
    sa.Column('deployment_id', sa.String(length=36), nullable=True),
    sa.Column('bucket_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('bucket_seconds', sa.Integer(), nullable=False),
    sa.Column('data_source', sa.String(length=16), nullable=False),
    sa.Column('requested_batch_size', sa.Float(), nullable=True),
    sa.Column('effective_batch_size', sa.Float(), nullable=True),
    sa.Column('avg_batch_size', sa.Float(), nullable=True),
    sa.Column('max_batch_size', sa.Integer(), nullable=True),
    sa.Column('configured_max_batch_size', sa.Integer(), nullable=True),
    sa.Column('queue_depth', sa.Float(), nullable=True),
    sa.Column('batch_formation_ms', sa.Float(), nullable=True),
    sa.Column('batch_efficiency', sa.Float(), nullable=True),
    sa.Column('gpu_utilization_pct', sa.Float(), nullable=True),
    sa.Column('throughput_rps', sa.Float(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['deployment_id'], ['deployments.id'], name=op.f('fk_batch_metrics_deployment_id_deployments'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_batch_metrics')),
    sa.UniqueConstraint('deployment_id', 'bucket_start', 'bucket_seconds', 'data_source', name='uq_batch_metrics_bucket')
    )
    with op.batch_alter_table('batch_metrics', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_batch_metrics_bucket_start'), ['bucket_start'], unique=False)
        batch_op.create_index(batch_op.f('ix_batch_metrics_data_source'), ['data_source'], unique=False)
        batch_op.create_index(batch_op.f('ix_batch_metrics_deployment_id'), ['deployment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_batch_metrics_id'), ['id'], unique=False)

    op.create_table('inference_metrics',
    sa.Column('deployment_id', sa.String(length=36), nullable=True),
    sa.Column('model_id', sa.String(length=36), nullable=True),
    sa.Column('bucket_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('bucket_seconds', sa.Integer(), nullable=False),
    sa.Column('data_source', sa.String(length=16), nullable=False),
    sa.Column('request_count', sa.Integer(), nullable=False),
    sa.Column('error_count', sa.Integer(), nullable=False),
    sa.Column('requests_per_second', sa.Float(), nullable=True),
    sa.Column('avg_latency_ms', sa.Float(), nullable=True),
    sa.Column('min_latency_ms', sa.Float(), nullable=True),
    sa.Column('max_latency_ms', sa.Float(), nullable=True),
    sa.Column('p50_latency_ms', sa.Float(), nullable=True),
    sa.Column('p90_latency_ms', sa.Float(), nullable=True),
    sa.Column('p95_latency_ms', sa.Float(), nullable=True),
    sa.Column('p99_latency_ms', sa.Float(), nullable=True),
    sa.Column('avg_queue_latency_ms', sa.Float(), nullable=True),
    sa.Column('avg_preprocess_latency_ms', sa.Float(), nullable=True),
    sa.Column('avg_execution_latency_ms', sa.Float(), nullable=True),
    sa.Column('avg_postprocess_latency_ms', sa.Float(), nullable=True),
    sa.Column('tokens_per_second', sa.Float(), nullable=True),
    sa.Column('input_tokens_per_second', sa.Float(), nullable=True),
    sa.Column('output_tokens_per_second', sa.Float(), nullable=True),
    sa.Column('total_input_tokens', sa.Integer(), nullable=False),
    sa.Column('total_output_tokens', sa.Integer(), nullable=False),
    sa.Column('avg_batch_size', sa.Float(), nullable=True),
    sa.Column('max_batch_size', sa.Integer(), nullable=True),
    sa.Column('avg_concurrency', sa.Float(), nullable=True),
    sa.Column('error_rate', sa.Float(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['deployment_id'], ['deployments.id'], name=op.f('fk_inference_metrics_deployment_id_deployments'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['model_id'], ['ml_models.id'], name=op.f('fk_inference_metrics_model_id_ml_models'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_inference_metrics')),
    sa.UniqueConstraint('deployment_id', 'bucket_start', 'bucket_seconds', 'data_source', name='uq_inference_metrics_bucket')
    )
    with op.batch_alter_table('inference_metrics', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_inference_metrics_bucket_start'), ['bucket_start'], unique=False)
        batch_op.create_index(batch_op.f('ix_inference_metrics_data_source'), ['data_source'], unique=False)
        batch_op.create_index(batch_op.f('ix_inference_metrics_deployment_id'), ['deployment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_inference_metrics_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_inference_metrics_model_id'), ['model_id'], unique=False)
        batch_op.create_index('ix_inference_metrics_source_bucket', ['data_source', 'bucket_start'], unique=False)

    op.create_table('inference_requests',
    sa.Column('deployment_id', sa.String(length=36), nullable=True),
    sa.Column('model_id', sa.String(length=36), nullable=True),
    sa.Column('gpu_id', sa.String(length=36), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('data_source', sa.String(length=16), nullable=False),
    sa.Column('total_latency_ms', sa.Float(), nullable=False),
    sa.Column('queue_latency_ms', sa.Float(), nullable=True),
    sa.Column('preprocess_latency_ms', sa.Float(), nullable=True),
    sa.Column('execution_latency_ms', sa.Float(), nullable=True),
    sa.Column('postprocess_latency_ms', sa.Float(), nullable=True),
    sa.Column('time_to_first_token_ms', sa.Float(), nullable=True),
    sa.Column('input_tokens', sa.Integer(), nullable=True),
    sa.Column('output_tokens', sa.Integer(), nullable=True),
    sa.Column('batch_size', sa.Integer(), nullable=True),
    sa.Column('concurrency', sa.Integer(), nullable=True),
    sa.Column('status_code', sa.Integer(), nullable=False),
    sa.Column('is_error', sa.Boolean(), nullable=False),
    sa.Column('error_type', sa.String(length=120), nullable=True),
    sa.Column('client_id', sa.String(length=120), nullable=True),
    sa.Column('trace_id', sa.String(length=64), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['deployment_id'], ['deployments.id'], name=op.f('fk_inference_requests_deployment_id_deployments'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['gpu_id'], ['gpus.id'], name=op.f('fk_inference_requests_gpu_id_gpus'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['model_id'], ['ml_models.id'], name=op.f('fk_inference_requests_model_id_ml_models'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_inference_requests'))
    )
    with op.batch_alter_table('inference_requests', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_inference_requests_data_source'), ['data_source'], unique=False)
        batch_op.create_index('ix_inference_requests_dep_time', ['deployment_id', 'started_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_inference_requests_deployment_id'), ['deployment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_inference_requests_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_inference_requests_is_error'), ['is_error'], unique=False)
        batch_op.create_index(batch_op.f('ix_inference_requests_model_id'), ['model_id'], unique=False)
        batch_op.create_index('ix_inference_requests_model_time', ['model_id', 'started_at'], unique=False)
        batch_op.create_index('ix_inference_requests_source_time', ['data_source', 'started_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_inference_requests_started_at'), ['started_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_inference_requests_trace_id'), ['trace_id'], unique=False)

    op.create_table('workloads',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('profile', sa.String(length=40), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('data_source', sa.String(length=16), nullable=False),
    sa.Column('deployment_id', sa.String(length=36), nullable=True),
    sa.Column('target_rps', sa.Float(), nullable=True),
    sa.Column('concurrency', sa.Integer(), nullable=True),
    sa.Column('batch_size', sa.Integer(), nullable=True),
    sa.Column('duration_seconds', sa.Integer(), nullable=True),
    sa.Column('scenario', sa.String(length=40), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('requests_generated', sa.Integer(), nullable=False),
    sa.Column('errors_generated', sa.Integer(), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('parameters', sa.Text(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['deployment_id'], ['deployments.id'], name=op.f('fk_workloads_deployment_id_deployments'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_workloads'))
    )
    with op.batch_alter_table('workloads', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_workloads_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_workloads_data_source'), ['data_source'], unique=False)
        batch_op.create_index(batch_op.f('ix_workloads_deployment_id'), ['deployment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_workloads_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_workloads_profile'), ['profile'], unique=False)
        batch_op.create_index(batch_op.f('ix_workloads_started_at'), ['started_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_workloads_status'), ['status'], unique=False)

    


def downgrade() -> None:
    # Initial schema for NVIDIA AI Performance Observatory.
    with op.batch_alter_table('workloads', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_workloads_status'))
        batch_op.drop_index(batch_op.f('ix_workloads_started_at'))
        batch_op.drop_index(batch_op.f('ix_workloads_profile'))
        batch_op.drop_index(batch_op.f('ix_workloads_id'))
        batch_op.drop_index(batch_op.f('ix_workloads_deployment_id'))
        batch_op.drop_index(batch_op.f('ix_workloads_data_source'))
        batch_op.drop_index(batch_op.f('ix_workloads_created_at'))

    op.drop_table('workloads')
    with op.batch_alter_table('inference_requests', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_inference_requests_trace_id'))
        batch_op.drop_index(batch_op.f('ix_inference_requests_started_at'))
        batch_op.drop_index('ix_inference_requests_source_time')
        batch_op.drop_index('ix_inference_requests_model_time')
        batch_op.drop_index(batch_op.f('ix_inference_requests_model_id'))
        batch_op.drop_index(batch_op.f('ix_inference_requests_is_error'))
        batch_op.drop_index(batch_op.f('ix_inference_requests_id'))
        batch_op.drop_index(batch_op.f('ix_inference_requests_deployment_id'))
        batch_op.drop_index('ix_inference_requests_dep_time')
        batch_op.drop_index(batch_op.f('ix_inference_requests_data_source'))

    op.drop_table('inference_requests')
    with op.batch_alter_table('inference_metrics', schema=None) as batch_op:
        batch_op.drop_index('ix_inference_metrics_source_bucket')
        batch_op.drop_index(batch_op.f('ix_inference_metrics_model_id'))
        batch_op.drop_index(batch_op.f('ix_inference_metrics_id'))
        batch_op.drop_index(batch_op.f('ix_inference_metrics_deployment_id'))
        batch_op.drop_index(batch_op.f('ix_inference_metrics_data_source'))
        batch_op.drop_index(batch_op.f('ix_inference_metrics_bucket_start'))

    op.drop_table('inference_metrics')
    with op.batch_alter_table('batch_metrics', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_batch_metrics_id'))
        batch_op.drop_index(batch_op.f('ix_batch_metrics_deployment_id'))
        batch_op.drop_index(batch_op.f('ix_batch_metrics_data_source'))
        batch_op.drop_index(batch_op.f('ix_batch_metrics_bucket_start'))

    op.drop_table('batch_metrics')
    with op.batch_alter_table('refresh_tokens', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_refresh_tokens_user_id'))
        batch_op.drop_index(batch_op.f('ix_refresh_tokens_token_hash'))
        batch_op.drop_index(batch_op.f('ix_refresh_tokens_id'))
        batch_op.drop_index(batch_op.f('ix_refresh_tokens_created_at'))

    op.drop_table('refresh_tokens')
    with op.batch_alter_table('gpu_processes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_gpu_processes_recorded_at'))
        batch_op.drop_index(batch_op.f('ix_gpu_processes_id'))
        batch_op.drop_index('ix_gpu_processes_gpu_time')
        batch_op.drop_index(batch_op.f('ix_gpu_processes_gpu_id'))
        batch_op.drop_index(batch_op.f('ix_gpu_processes_data_source'))

    op.drop_table('gpu_processes')
    with op.batch_alter_table('gpu_metrics', schema=None) as batch_op:
        batch_op.drop_index('ix_gpu_metrics_source_time')
        batch_op.drop_index(batch_op.f('ix_gpu_metrics_recorded_at'))
        batch_op.drop_index(batch_op.f('ix_gpu_metrics_id'))
        batch_op.drop_index('ix_gpu_metrics_gpu_time')
        batch_op.drop_index(batch_op.f('ix_gpu_metrics_gpu_id'))
        batch_op.drop_index(batch_op.f('ix_gpu_metrics_data_source'))

    op.drop_table('gpu_metrics')
    with op.batch_alter_table('deployments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_deployments_status'))
        batch_op.drop_index('ix_deployments_model_status')
        batch_op.drop_index(batch_op.f('ix_deployments_model_id'))
        batch_op.drop_index(batch_op.f('ix_deployments_id'))
        batch_op.drop_index(batch_op.f('ix_deployments_data_source'))
        batch_op.drop_index(batch_op.f('ix_deployments_created_at'))

    op.drop_table('deployments')
    with op.batch_alter_table('api_keys', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_api_keys_prefix'))
        batch_op.drop_index(batch_op.f('ix_api_keys_owner_id'))
        batch_op.drop_index(batch_op.f('ix_api_keys_key_hash'))
        batch_op.drop_index(batch_op.f('ix_api_keys_id'))
        batch_op.drop_index(batch_op.f('ix_api_keys_created_at'))

    op.drop_table('api_keys')
    with op.batch_alter_table('alerts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_alerts_triggered_at'))
        batch_op.drop_index('ix_alerts_state_time')
        batch_op.drop_index(batch_op.f('ix_alerts_state'))
        batch_op.drop_index('ix_alerts_source_state')
        batch_op.drop_index(batch_op.f('ix_alerts_severity'))
        batch_op.drop_index(batch_op.f('ix_alerts_rule_id'))
        batch_op.drop_index(batch_op.f('ix_alerts_id'))
        batch_op.drop_index(batch_op.f('ix_alerts_entity_id'))
        batch_op.drop_index(batch_op.f('ix_alerts_data_source'))
        batch_op.drop_index(batch_op.f('ix_alerts_created_at'))
        batch_op.drop_index(batch_op.f('ix_alerts_condition'))

    op.drop_table('alerts')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index('ix_users_role_active')
        batch_op.drop_index(batch_op.f('ix_users_id'))
        batch_op.drop_index(batch_op.f('ix_users_email'))
        batch_op.drop_index(batch_op.f('ix_users_created_at'))

    op.drop_table('users')
    with op.batch_alter_table('system_metrics', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_system_metrics_recorded_at'))
        batch_op.drop_index(batch_op.f('ix_system_metrics_id'))
        batch_op.drop_index('ix_system_metrics_host_time')
        batch_op.drop_index(batch_op.f('ix_system_metrics_host'))
        batch_op.drop_index(batch_op.f('ix_system_metrics_data_source'))

    op.drop_table('system_metrics')
    with op.batch_alter_table('pricing_profiles', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pricing_profiles_name'))
        batch_op.drop_index(batch_op.f('ix_pricing_profiles_is_default'))
        batch_op.drop_index(batch_op.f('ix_pricing_profiles_id'))
        batch_op.drop_index(batch_op.f('ix_pricing_profiles_gpu_model'))
        batch_op.drop_index(batch_op.f('ix_pricing_profiles_created_at'))

    op.drop_table('pricing_profiles')
    with op.batch_alter_table('ml_models', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ml_models_name'))
        batch_op.drop_index(batch_op.f('ix_ml_models_id'))
        batch_op.drop_index(batch_op.f('ix_ml_models_data_source'))
        batch_op.drop_index(batch_op.f('ix_ml_models_created_at'))

    op.drop_table('ml_models')
    with op.batch_alter_table('gpus', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_gpus_uuid'))
        batch_op.drop_index('ix_gpus_source_index')
        batch_op.drop_index(batch_op.f('ix_gpus_last_seen_at'))
        batch_op.drop_index(batch_op.f('ix_gpus_id'))
        batch_op.drop_index(batch_op.f('ix_gpus_host'))
        batch_op.drop_index(batch_op.f('ix_gpus_data_source'))
        batch_op.drop_index(batch_op.f('ix_gpus_created_at'))

    op.drop_table('gpus')
    with op.batch_alter_table('diagnoses', schema=None) as batch_op:
        batch_op.drop_index('ix_diagnoses_source_time')
        batch_op.drop_index(batch_op.f('ix_diagnoses_severity'))
        batch_op.drop_index(batch_op.f('ix_diagnoses_kind'))
        batch_op.drop_index(batch_op.f('ix_diagnoses_id'))
        batch_op.drop_index(batch_op.f('ix_diagnoses_generated_at'))
        batch_op.drop_index(batch_op.f('ix_diagnoses_entity_id'))
        batch_op.drop_index(batch_op.f('ix_diagnoses_data_source'))
        batch_op.drop_index(batch_op.f('ix_diagnoses_created_at'))

    op.drop_table('diagnoses')
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_audit_logs_request_id'))
        batch_op.drop_index(batch_op.f('ix_audit_logs_occurred_at'))
        batch_op.drop_index(batch_op.f('ix_audit_logs_id'))
        batch_op.drop_index(batch_op.f('ix_audit_logs_actor_id'))
        batch_op.drop_index(batch_op.f('ix_audit_logs_action'))
        batch_op.drop_index('ix_audit_action_time')

    op.drop_table('audit_logs')
    with op.batch_alter_table('anomalies', schema=None) as batch_op:
        batch_op.drop_index('ix_anomalies_source_time')
        batch_op.drop_index(batch_op.f('ix_anomalies_severity'))
        batch_op.drop_index('ix_anomalies_metric_time')
        batch_op.drop_index(batch_op.f('ix_anomalies_metric_kind'))
        batch_op.drop_index(batch_op.f('ix_anomalies_id'))
        batch_op.drop_index(batch_op.f('ix_anomalies_entity_id'))
        batch_op.drop_index(batch_op.f('ix_anomalies_detected_at'))
        batch_op.drop_index(batch_op.f('ix_anomalies_data_source'))
        batch_op.drop_index(batch_op.f('ix_anomalies_created_at'))

    op.drop_table('anomalies')
    with op.batch_alter_table('alert_rules', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_alert_rules_name'))
        batch_op.drop_index(batch_op.f('ix_alert_rules_is_enabled'))
        batch_op.drop_index(batch_op.f('ix_alert_rules_id'))
        batch_op.drop_index(batch_op.f('ix_alert_rules_data_source'))
        batch_op.drop_index(batch_op.f('ix_alert_rules_created_at'))

    op.drop_table('alert_rules')
    
