mod db;
mod auth;
mod models;

use std::env;
use std::net::SocketAddr;

use axum::{
    routing::{get, post},
    Router,
};
use dotenvy::dotenv;
use tower_http::services::ServeDir;

#[tokio::main]
async fn main() {
    dotenv().ok();

    let pool = db::init_db().await.expect("failed to init db");

    let app = Router::new()
        .route("/", get(handlers::index))
        .route("/health", get(handlers::health))
        .route("/register", post(auth::register))
        .route("/login", post(auth::login))
        .nest_service("/static", ServeDir::new("static"))
        .with_state(pool);

    let port = env::var("PORT").unwrap_or_else(|_| "3000".to_string());
    let addr: SocketAddr = format!("0.0.0.0:{}", port).parse().unwrap();
    println!("Listening on {}", addr);
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}

mod handlers {
    use askama_axum::Template;
    use axum::response::Html;

    #[derive(Template)]
    #[template(path = "index.html")]
    struct IndexTemplate {
        user: Option<String>,
    }

    pub async fn index() -> Html<IndexTemplate> {
        Html(IndexTemplate { user: None })
    }

    pub async fn health() -> &'static str {
        "{\"status\":\"ok\"}"
    }
}
