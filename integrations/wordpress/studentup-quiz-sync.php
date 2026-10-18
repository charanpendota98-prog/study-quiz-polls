<?php
/**
 * StudentUp Quiz Sync — WordPress side bridge (OPTIONAL, one-time setup).
 *
 * What it does:
 *   Registers a private REST route  POST /wp-json/studentup/v1/quiz
 *   that receives the daily quiz bank exported from the StudentUp
 *   platform dashboard (📤 Today's Quiz → WP Format Export, or automated
 *   with an Application Password) and stores it in wp_options. The theme
 *   helper studentup_synced_quiz_items() returns the synced items so
 *   inc/quiz.php can prefer them over the hardcoded fallback bank.
 *
 * Security:
 *   - Only users who can edit_posts (admins/editors, or an Application
 *     Password of such a user) may push. Nothing is public-writable.
 *   - Payload is sanitized field-by-field; max 50 questions.
 *
 * Install (one time):
 *   1. Copy this file into the theme:  wordpress-theme/studentup/inc/
 *   2. In functions.php add:           require_once get_template_directory() . '/inc/studentup-quiz-sync.php';
 *   3. (Optional, to actually use synced items) in inc/quiz.php, at the
 *      top of studentup_quiz_bank(), add:
 *          $synced = studentup_synced_quiz_items();
 *          if ($synced) { return $synced; }
 *
 * Push example (from the server or any cron):
 *   curl -X POST https://studentup.in/wp-json/studentup/v1/quiz \
 *     -u "admin:APP_PASSWORD" -H "Content-Type: application/json" \
 *     --data @studentup_daily_quiz_2026-10-17.json
 */

if (!defined('ABSPATH')) {
    exit;
}

add_action('rest_api_init', function () {
    register_rest_route('studentup/v1', '/quiz', array(
        'methods'             => 'POST',
        'permission_callback' => function () {
            return current_user_can('edit_posts');
        },
        'callback'            => 'studentup_quiz_sync_receive',
    ));
});

function studentup_quiz_sync_receive(WP_REST_Request $req) {
    $data = $req->get_json_params();
    $items_in = isset($data['questions']) && is_array($data['questions'])
        ? $data['questions'] : array();
    $items = array();
    foreach (array_slice($items_in, 0, 50) as $row) {
        if (!is_array($row) || empty($row['q']) || empty($row['a']) || !is_array($row['a'])) {
            continue;
        }
        $opts = array_values(array_map('sanitize_text_field', $row['a']));
        if (count($opts) < 2) {
            continue;
        }
        $c = isset($row['c']) ? (int) $row['c'] : 0;
        if ($c < 0 || $c >= count($opts)) {
            $c = 0;
        }
        $items[] = array(
            'q'   => sanitize_text_field($row['q']),
            'a'   => $opts,
            'c'   => $c,
            'why' => isset($row['why']) ? sanitize_text_field($row['why']) : '',
            'cat' => isset($row['cat']) ? sanitize_text_field($row['cat']) : 'General',
            'src' => isset($row['src']) ? sanitize_text_field($row['src']) : 'StudentUp',
            'exam'=> isset($row['exam']) ? sanitize_text_field($row['exam']) : 'all',
        );
    }
    if (!$items) {
        return new WP_Error('empty_bank', 'No valid questions in payload', array('status' => 422));
    }
    update_option('studentup_synced_quiz_bank', $items, false);
    update_option('studentup_synced_quiz_date', isset($data['date']) ? sanitize_text_field($data['date']) : '', false);
    return array('ok' => true, 'stored' => count($items));
}

/**
 * Items pushed from the StudentUp platform (or empty array).
 * inc/quiz.php may prefer these over its hardcoded fallback bank.
 */
function studentup_synced_quiz_items() {
    $items = get_option('studentup_synced_quiz_bank', array());
    return is_array($items) ? $items : array();
}
