#!/usr/bin/env Rscript
#
# Generic random-effects meta-analysis over extraction/studies.csv.
# Deliberately outside the LLM router: the number that ends up in the
# manuscript comes from this script and rma(), never from a model.
#
# Usage:
#   Rscript analysis/meta_analysis.R \
#     --input results/<review>/extraction/studies.csv \
#     --outcome mortality_30d \
#     --measure OR \
#     --out-dir results/<review>/analysis
#
# For a binary outcome (measure OR/RR/RD), studies.csv must have columns:
#   <outcome>_events_intervention, <outcome>_n_intervention,
#   <outcome>_events_control,      <outcome>_n_control
#
# For a continuous outcome (measure MD/SMD), studies.csv must have columns:
#   <outcome>_mean_intervention, <outcome>_sd_intervention, <outcome>_n_intervention,
#   <outcome>_mean_control,      <outcome>_sd_control,      <outcome>_n_control
#
# A `subgroup` column, if present, triggers a subgroup analysis automatically.
#
# Writes: <out-dir>/results.json, <out-dir>/figures/forest_<outcome>.pdf,
#         <out-dir>/figures/funnel_<outcome>.pdf

suppressPackageStartupMessages({
  if (!requireNamespace("metafor", quietly = TRUE)) {
    stop("Package 'metafor' is required. Install with: install.packages('metafor')")
  }
  if (!requireNamespace("jsonlite", quietly = TRUE)) {
    stop("Package 'jsonlite' is required. Install with: install.packages('jsonlite')")
  }
  library(metafor)
  library(jsonlite)
})

parse_args <- function(args) {
  opts <- list(input = NULL, outcome = NULL, measure = "OR", out_dir = NULL, title = NULL)
  for (a in args) {
    kv <- regmatches(a, regexec("^--([a-zA-Z-]+)=(.*)$", a))[[1]]
    if (length(kv) == 3) {
      key <- gsub("-", "_", kv[2])
      opts[[key]] <- kv[3]
    }
  }
  if (is.null(opts$input) || is.null(opts$outcome) || is.null(opts$out_dir)) {
    stop("Required: --input=<studies.csv> --outcome=<column_prefix> --out-dir=<dir> [--measure=OR|RR|RD|MD|SMD] [--title=...]")
  }
  opts
}

opts <- parse_args(commandArgs(trailingOnly = TRUE))
measure <- toupper(opts$measure)
binary_measures <- c("OR", "RR", "RD")
continuous_measures <- c("MD", "SMD")
if (!(measure %in% c(binary_measures, continuous_measures))) {
  stop(sprintf("Unsupported --measure '%s'. Use one of: %s", measure,
               paste(c(binary_measures, continuous_measures), collapse = ", ")))
}

dat <- read.csv(opts$input, stringsAsFactors = FALSE)
if (!"title" %in% names(dat)) stop("studies.csv must have a 'title' column")

fig_dir <- file.path(opts$out_dir, "figures")
dir.create(fig_dir, recursive = TRUE, showWarnings = FALSE)

col <- function(suffix) paste0(opts$outcome, "_", suffix)

if (measure %in% binary_measures) {
  needed <- col(c("events_intervention", "n_intervention", "events_control", "n_control"))
  missing <- needed[!needed %in% names(dat)]
  if (length(missing) > 0) stop(sprintf("Missing columns for binary outcome '%s': %s", opts$outcome, paste(missing, collapse = ", ")))
  complete <- stats::complete.cases(dat[, needed])
  dat_use <- dat[complete, ]
  es <- escalc(
    measure = measure,
    ai = dat_use[[col("events_intervention")]], n1i = dat_use[[col("n_intervention")]],
    ci = dat_use[[col("events_control")]],      n2i = dat_use[[col("n_control")]],
    slab = dat_use$title
  )
} else {
  needed <- col(c("mean_intervention", "sd_intervention", "n_intervention",
                   "mean_control", "sd_control", "n_control"))
  missing <- needed[!needed %in% names(dat)]
  if (length(missing) > 0) stop(sprintf("Missing columns for continuous outcome '%s': %s", opts$outcome, paste(missing, collapse = ", ")))
  complete <- stats::complete.cases(dat[, needed])
  dat_use <- dat[complete, ]
  es <- escalc(
    measure = measure,
    m1i = dat_use[[col("mean_intervention")]], sd1i = dat_use[[col("sd_intervention")]], n1i = dat_use[[col("n_intervention")]],
    m2i = dat_use[[col("mean_control")]],      sd2i = dat_use[[col("sd_control")]],      n2i = dat_use[[col("n_control")]],
    slab = dat_use$title
  )
}

n_excluded <- sum(!complete)
if (n_excluded > 0) {
  message(sprintf("Note: %d/%d studies excluded from '%s' — incomplete data for this outcome.",
                   n_excluded, nrow(dat), opts$outcome))
}
if (nrow(es) < 2) {
  stop(sprintf("Only %d study has usable data for outcome '%s' — a meta-analysis needs at least 2.", nrow(es), opts$outcome))
}

fit <- rma(yi, vi, data = es, method = "REML")

subgroup_results <- NULL
if ("subgroup" %in% names(dat_use)) {
  groups <- unique(dat_use$subgroup)
  subgroup_results <- lapply(groups, function(g) {
    idx <- dat_use$subgroup == g
    if (sum(idx) < 2) return(NULL)
    fit_g <- rma(yi, vi, data = es[idx, ], method = "REML")
    list(
      subgroup = g, k = fit_g$k,
      estimate = unname(fit_g$b[1, 1]), ci_lb = fit_g$ci.lb, ci_ub = fit_g$ci.ub,
      i2 = fit_g$I2, tau2 = fit_g$tau2
    )
  })
  subgroup_results <- Filter(Negate(is.null), subgroup_results)
}

egger <- tryCatch(regtest(fit), error = function(e) NULL)

forest_path <- file.path(fig_dir, sprintf("forest_%s.pdf", opts$outcome))
pdf(forest_path, width = 9, height = max(4, 1.2 + 0.3 * nrow(es)))
forest(fit, header = TRUE,
       xlab = sprintf("%s (95%% CI) — %s", measure, opts$outcome),
       mlab = sprintf("RE Model (Q=%.2f, df=%d, p=%.3f; I^2=%.1f%%)", fit$QE, fit$k - 1, fit$QEp, fit$I2))
title(main = if (!is.null(opts$title)) opts$title else sprintf("Forest plot — %s", opts$outcome))
invisible(dev.off())

funnel_path <- file.path(fig_dir, sprintf("funnel_%s.pdf", opts$outcome))
pdf(funnel_path, width = 6, height = 6)
funnel(fit, main = sprintf("Funnel plot — %s", opts$outcome))
invisible(dev.off())

is_log_scale <- measure %in% c("OR", "RR")
result <- list(
  outcome = opts$outcome,
  measure = measure,
  k = fit$k,
  k_excluded_incomplete_data = n_excluded,
  estimate = unname(fit$b[1, 1]),
  estimate_exp = if (is_log_scale) exp(unname(fit$b[1, 1])) else NULL,
  ci_lb = fit$ci.lb,
  ci_ub = fit$ci.ub,
  ci_lb_exp = if (is_log_scale) exp(fit$ci.lb) else NULL,
  ci_ub_exp = if (is_log_scale) exp(fit$ci.ub) else NULL,
  p_value = fit$pval,
  tau2 = fit$tau2,
  i2 = fit$I2,
  h2 = fit$H2,
  q_stat = fit$QE,
  q_df = fit$k - 1,
  q_pvalue = fit$QEp,
  egger_p_value = if (!is.null(egger)) egger$pval else NA,
  method = "REML random-effects (metafor::rma)",
  subgroups = subgroup_results,
  studies = lapply(seq_len(nrow(es)), function(i) list(
    title = dat_use$title[i],
    yi = unname(es$yi[i]),
    vi = unname(es$vi[i]),
    weight_pct = unname(weights(fit)[i])
  )),
  forest_plot = forest_path,
  funnel_plot = funnel_path,
  generated_at = format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
)

results_path <- file.path(opts$out_dir, sprintf("results_%s.json", opts$outcome))
# null = "null" matters here: several fields above are R NULL when not
# applicable (estimate_exp etc. for MD/SMD, subgroups with no subgroup
# column) — jsonlite's default would serialize those as `{}`, not JSON null.
write(toJSON(result, auto_unbox = TRUE, pretty = TRUE, na = "null", null = "null"), results_path)

cat(sprintf(
  "\n%s pooled effect for '%s': %.3f [%.3f, %.3f] (k=%d studies, I^2=%.1f%%, Egger p=%s)\n",
  measure, opts$outcome, result$estimate, result$ci_lb, result$ci_ub, fit$k, fit$I2,
  if (!is.null(egger)) sprintf("%.3f", egger$pval) else "NA"
))
cat(sprintf("Wrote: %s\n", results_path))
cat(sprintf("Wrote: %s\n", forest_path))
cat(sprintf("Wrote: %s\n", funnel_path))
