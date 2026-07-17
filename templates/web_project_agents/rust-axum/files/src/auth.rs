use std::env;

use axum::{
    extract::State,
    http::StatusCode,
    response::Json,
    Extension,
};
use bcrypt::{hash, verify, DEFAULT_COST};
use jsonwebtoken::{decode, encode, DecodingKey, EncodingKey, Header, Validation};
use serde_json::{json, Value};
use sqlx::SqlitePool;

use crate::models::{Claims, LoginRequest, RegisterRequest, UserResponse};

pub async fn register(
    State(pool): State<SqlitePool>,
    Json(req): Json<RegisterRequest>,
) -> Result<Json<Value>, StatusCode> {
    let password_hash = hash(&req.password, DEFAULT_COST).map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    let result = sqlx::query_as::<_, (i64,)>(
        "INSERT INTO users (username, password_hash) VALUES (?, ?) RETURNING id",
    )
    .bind(&req.username)
    .bind(&password_hash)
    .fetch_one(&pool)
    .await;

    match result {
        Ok((id,)) => Ok(Json(json!({"id": id, "username": req.username}))),
        Err(_) => Err(StatusCode::BAD_REQUEST),
    }
}

pub async fn login(
    State(pool): State<SqlitePool>,
    Json(req): Json<LoginRequest>,
) -> Result<Json<Value>, StatusCode> {
    let row: Option<(i64, String)> = sqlx::query_as("SELECT id, password_hash FROM users WHERE username = ?")
        .bind(&req.username)
        .fetch_optional(&pool)
        .await
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    let (_, password_hash) = row.ok_or(StatusCode::UNAUTHORIZED)?;
    if !verify(&req.password, &password_hash).map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)? {
        return Err(StatusCode::UNAUTHORIZED);
    }

    let secret = env::var("JWT_SECRET").unwrap_or_else(|_| "change-me".to_string());
    let claims = Claims {
        sub: req.username.clone(),
        exp: usize::MAX,
    };
    let token = encode(
        &Header::default(),
        &claims,
        &EncodingKey::from_secret(secret.as_bytes()),
    )
    .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    Ok(Json(json!({"token": token})))
}

pub async fn me(Extension(username): Extension<String>) -> Json<Value> {
    Json(json!({"username": username}))
}
