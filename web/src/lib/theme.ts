export const THEME_KEY = "pyrasca-theme";

/**
 * Runs in <head> before the page paints: applies a theme the visitor picked earlier
 * with the sun/moon button, so a saved choice never flashes the other theme.
 * Without one, the CSS follows the device setting.
 */
export const themeScript = `try{var t=localStorage.getItem("${THEME_KEY}");if(t==="dark"||t==="light")document.documentElement.dataset.theme=t}catch(e){}`;
