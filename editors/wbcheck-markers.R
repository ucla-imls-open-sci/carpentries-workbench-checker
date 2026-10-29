# Show wbcheck findings in RStudio's Markers pane. Positron and VS Code do not
# need this: use the problem matcher or SARIF file described in editors/README.md.
#
#   source("path/to/wbcheck-markers.R")
#   wbcheck_markers()                  # reads .wbcheck/results.json in the project
#   wbcheck_markers(refresh = TRUE)    # runs `wbcheck check` first
#
# Needs the jsonlite package, and rstudioapi when it runs inside RStudio.

# Findings from a results file as a data frame in rstudioapi::sourceMarkers()'s
# shape: type, file (full path), line, column, message. Plain R, so it can be
# tested without RStudio.
wbcheck_marker_frame <- function(lesson = ".", results = NULL, min_severity = "info") {
  lesson <- normalizePath(lesson, mustWork = TRUE)
  results <- results %||% file.path(lesson, ".wbcheck", "results.json")
  if (!file.exists(results)) {
    stop("No results at ", results, ". Run `wbcheck check ", lesson, "` first, or use refresh = TRUE.")
  }
  data <- jsonlite::fromJSON(results, simplifyVector = TRUE)
  findings <- data$findings
  empty <- data.frame(type = character(), file = character(), line = integer(),
                      column = integer(), message = character(), stringsAsFactors = FALSE)
  if (is.null(findings) || NROW(findings) == 0) return(empty)
  rank <- c(error = 1, warning = 2, info = 3)
  findings <- findings[!is.na(findings$location) & rank[findings$severity] <= rank[[min_severity]], , drop = FALSE]
  if (NROW(findings) == 0) return(empty)
  line <- ifelse(is.na(findings$line), 1L, as.integer(findings$line))
  code <- ifelse(is.na(findings$code), findings$category, findings$code)
  data.frame(
    type = findings$severity,
    file = file.path(lesson, findings$location),
    line = line,
    column = 1L,
    message = paste0("[", code, "] ", gsub("[[:space:]]+", " ", findings$message)),
    stringsAsFactors = FALSE
  )
}

wbcheck_markers <- function(lesson = ".", refresh = FALSE, min_severity = "info") {
  if (!requireNamespace("rstudioapi", quietly = TRUE) || !rstudioapi::isAvailable("0.99.225")) {
    stop("This needs RStudio 0.99.225 or newer (rstudioapi::sourceMarkers). ",
         "In other editors use `wbcheck report --lines -`; see editors/README.md.")
  }
  if (refresh) {
    status <- system2("wbcheck", c("check", shQuote(lesson), "--quiet"), stdout = FALSE, stderr = FALSE)
    if (status > 1) stop("`wbcheck check` failed (exit ", status, "); run it in a terminal to see why.")
  }
  markers <- wbcheck_marker_frame(lesson, min_severity = min_severity)
  rstudioapi::sourceMarkers("wbcheck", markers, basePath = normalizePath(lesson), autoSelect = "first")
  invisible(markers)
}

`%||%` <- function(a, b) if (is.null(a)) b else a
