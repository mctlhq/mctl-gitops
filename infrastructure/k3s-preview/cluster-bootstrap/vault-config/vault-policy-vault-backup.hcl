# Policy for the vault-backup CronJob.
# Allows reading raft snapshots so the job can call
# `vault operator raft snapshot save`.
path "sys/storage/raft/snapshot" {
  capabilities = ["read"]
}
